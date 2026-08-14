"""Quant-analytics endpoints (Phase 5, D5).

Three additive, read-only endpoints hanging off a system:

* ``GET /systems/{id}/topography``  — one topography grid per stored
  ``parameter_sweeps`` row (``grids: []`` when the system has no sweeps).
* ``GET /systems/{id}/walkforward`` — rolling IS/OOS windows over the system's
  trades; ``pct_positive`` is returned in percent (the service reports a
  fraction, converted here).
* ``GET /systems/{id}/montecarlo``  — seeded bootstrap of the system's R
  values.

All three 404 on an unknown system id; empty data yields a 200 with
nulls/empty arrays (never an error). The heavy lifting lives in the pure,
DB-free ``app.services.quant`` service.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import ParameterSweep, System, Trade
from app.schemas.quant import (
    MonteCarloResponse,
    TopographyResponse,
    WalkForwardResponse,
)
from app.services import quant

router = APIRouter(tags=["quant"])


def _get_system_or_404(db: Session, system_id: int) -> System:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail=f"system {system_id} not found")
    return system


def _system_trades(db: Session, system_id: int) -> list[Trade]:
    return list(
        db.execute(
            select(Trade).where(Trade.system_id == system_id)
        ).scalars()
    )


@router.get("/systems/{system_id}/topography", response_model=TopographyResponse)
def get_topography(
    system_id: int, db: Session = Depends(get_db)
) -> TopographyResponse:
    _get_system_or_404(db, system_id)

    sweeps = list(
        db.execute(
            select(ParameterSweep)
            .where(ParameterSweep.system_id == system_id)
            .order_by(ParameterSweep.id)
        ).scalars()
    )

    grids = []
    for sweep in sweeps:
        topo = quant.topography(sweep.param_x, sweep.param_y, sweep.points or [])
        grids.append(
            {
                "id": sweep.id,
                "label": sweep.label,
                "metric": sweep.metric,
                **topo,
            }
        )

    # All currently stored sweeps are pre-gate (DECISIONS Phase 5, point 5); the
    # field exists so later post-gate sweeps become distinguishable.
    return TopographyResponse(system_id=system_id, pre_gate=True, grids=grids)


@router.get("/systems/{system_id}/walkforward", response_model=WalkForwardResponse)
def get_walkforward(
    system_id: int,
    is_months: int = Query(default=6, ge=1),
    oos_months: int = Query(default=3, ge=1),
    step_months: Optional[int] = Query(default=None, ge=1),
    min_oos_trades: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> WalkForwardResponse:
    _get_system_or_404(db, system_id)

    trades = _system_trades(db, system_id)
    result = quant.walk_forward(
        trades,
        is_months=is_months,
        oos_months=oos_months,
        step_months=step_months,
        min_oos_trades=min_oos_trades,
    )

    # D5: pct_positive is expressed in percent; the service returns a fraction.
    pct = result["pct_positive"]
    result["pct_positive"] = None if pct is None else pct * 100

    return WalkForwardResponse(system_id=system_id, **result)


@router.get("/systems/{system_id}/montecarlo", response_model=MonteCarloResponse)
def get_montecarlo(
    system_id: int,
    n: int = Query(default=1000, ge=1, le=10000),
    seed: int = Query(default=42),
    horizon: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> MonteCarloResponse:
    _get_system_or_404(db, system_id)

    r_values = [t.r_value for t in _system_trades(db, system_id) if t.r_value is not None]
    result = quant.monte_carlo(
        r_values, n_iterations=n, seed=seed, horizon=horizon
    )

    return MonteCarloResponse(
        system_id=system_id,
        n_iterations=n,
        seed=seed,
        n_trades=len(r_values),
        **result,
    )
