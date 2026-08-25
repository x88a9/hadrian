"""Strategy CRUD, versioning, validation and backtesting.

Backtests run synchronously. A few thousand bars through the engine is
sub-second, and a Python strategy adds one process spawn on top of that, so a
job queue would be machinery in front of a wait nobody notices. Sweeps (E4) are
the case that will need one, and they can bring it with them rather than the
single-run path paying for it now.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.data.cache import CachedCandleSource, CandleCache
from app.data.candles import CandleDataError, CandleSource
from app.data.hyperliquid import HyperliquidInfoSource
from app.models.strategy import BacktestRun, Strategy, StrategyVersion
from app.schemas.strategy import (
    BacktestRequest,
    BacktestRunOut,
    BacktestRunSummaryOut,
    StrategyCreate,
    StrategyDetailOut,
    StrategyDuplicate,
    StrategySummaryOut,
    StrategyUpdate,
    SweepOut,
    SweepRequest,
    ValidateRequest,
    ValidateResponse,
)
from app.services import strategy_service, sweep_service
from app.services.strategy_service import StrategyConflict, StrategyServiceError
from app.services.sweep_service import SweepTooLarge
from app.strategy.definition import StrategyDefinition, StrategyDefinitionError

router = APIRouter(tags=["strategies"])


def get_candle_source() -> CandleSource:
    """The bars a backtest runs on: the read-only ``/info`` endpoint behind a
    local cache.

    A FastAPI dependency rather than a module-level singleton so that tests can
    override it with a fixture, which is the only way to keep the API suite off
    the network.
    """
    return CachedCandleSource(
        HyperliquidInfoSource(settings.HL_INFO_URL),
        CandleCache(settings.CANDLE_CACHE_DIR),
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_strategy(db: Session, strategy_id: int) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"strategy {strategy_id} not found")
    return strategy


def _last_run(db: Session, strategy_id: int) -> BacktestRun | None:
    return db.scalar(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy_id, BacktestRun.status == "ok")
        .order_by(desc(BacktestRun.created_at), desc(BacktestRun.id))
        .limit(1)
    )


def _summary(db: Session, strategy: Strategy) -> dict:
    run = _last_run(db, strategy.id)
    total_r = None
    if run is not None and run.metrics:
        total_r = (run.metrics.get("all") or {}).get("total_r")
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "asset": strategy.asset,
        "timeframe": strategy.timeframe,
        "rules": strategy.rules,
        "current_version": strategy.current_version,
        "updated_at": strategy.updated_at,
        "last_backtest_at": run.created_at if run else None,
        "last_total_r": total_r,
    }


def _detail(db: Session, strategy: Strategy) -> dict:
    versions = db.scalars(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy.id)
        .order_by(desc(StrategyVersion.version))
    ).all()
    current = next(
        (v for v in versions if v.version == strategy.current_version), None
    )
    return {
        **_summary(db, strategy),
        "definition": current.definition if current else {},
        "versions": [StrategyVersionOut_from(v) for v in versions],
    }


def StrategyVersionOut_from(version: StrategyVersion) -> dict:
    return {
        "version": version.version,
        "definition": version.definition,
        "note": version.note,
        "created_at": version.created_at,
    }


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/strategies", response_model=list[StrategySummaryOut])
def list_strategies(db: Session = Depends(get_db)):
    strategies = db.scalars(select(Strategy).order_by(Strategy.name)).all()
    return [_summary(db, s) for s in strategies]


@router.post(
    "/strategies", response_model=StrategyDetailOut, status_code=status.HTTP_201_CREATED
)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)):
    try:
        strategy = strategy_service.create_strategy(
            db, payload.name, payload.definition, payload.description
        )
    except StrategyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _detail(db, strategy)


@router.get("/strategies/{strategy_id}", response_model=StrategyDetailOut)
def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    return _detail(db, _get_strategy(db, strategy_id))


@router.put("/strategies/{strategy_id}", response_model=StrategyDetailOut)
def update_strategy(
    strategy_id: int, payload: StrategyUpdate, db: Session = Depends(get_db)
):
    strategy = _get_strategy(db, strategy_id)
    strategy_service.save_version(db, strategy, payload.definition, payload.note)
    return _detail(db, strategy)


@router.post("/strategies/{strategy_id}/duplicate", response_model=StrategyDetailOut,
             status_code=status.HTTP_201_CREATED)
def duplicate_strategy(
    strategy_id: int, payload: StrategyDuplicate, db: Session = Depends(get_db)
):
    strategy = _get_strategy(db, strategy_id)
    try:
        copy = strategy_service.duplicate_strategy(db, strategy, payload.name)
    except StrategyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _detail(db, copy)


@router.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    strategy = _get_strategy(db, strategy_id)
    db.delete(strategy)
    db.commit()


@router.post("/strategies/validate", response_model=ValidateResponse)
def validate_definition(payload: ValidateRequest):
    """Parse a definition and report what is wrong with it, without storing it.

    Returns 200 with ``ok: false`` rather than a 4xx: the client is asking a
    question about a draft, and a draft being invalid is the expected answer,
    not a failed request.
    """
    try:
        definition = StrategyDefinition.from_json_dict(payload.definition)
    except StrategyDefinitionError as exc:
        return ValidateResponse(ok=False, errors=_readable_errors(exc))
    return ValidateResponse(ok=True, definition=definition)


def _readable_errors(exc: Exception) -> list[str]:
    """One line per problem.

    Pydantic reports several failures at once, separated by newlines, and a UI
    that shows them as a single paragraph is much less useful than one that
    shows a list.
    """
    text = str(exc)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines or [text]


@router.get(
    "/strategies/{strategy_id}/versions/{version}", response_model=dict
)
def get_version(strategy_id: int, version: int, db: Session = Depends(get_db)):
    strategy = _get_strategy(db, strategy_id)
    try:
        stored = strategy_service.version_or_404(db, strategy, version)
    except StrategyServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StrategyVersionOut_from(stored)


@router.post("/strategies/{strategy_id}/backtest", response_model=BacktestRunOut)
def run_backtest(
    strategy_id: int,
    payload: BacktestRequest,
    db: Session = Depends(get_db),
    source: CandleSource = Depends(get_candle_source),
):
    strategy = _get_strategy(db, strategy_id)
    try:
        run = strategy_service.run_and_record(
            db,
            strategy,
            source,
            version=payload.version,
            start=_as_utc(payload.start),
            end=_as_utc(payload.end),
            overrides=payload.overrides,
            persist=payload.persist,
        )
    except StrategyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StrategyServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CandleDataError as exc:
        # Not the strategy's fault and not a 500: the bars could not be got.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return run


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime from the wire.

    The alternative — letting a naive value through — means the candle source
    compares it against timezone-aware bar timestamps and raises somewhere far
    from the request that caused it.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get(
    "/strategies/{strategy_id}/backtests", response_model=list[BacktestRunSummaryOut]
)
def list_backtests(strategy_id: int, db: Session = Depends(get_db)):
    _get_strategy(db, strategy_id)
    return db.scalars(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy_id)
        .order_by(desc(BacktestRun.created_at), desc(BacktestRun.id))
    ).all()


@router.get("/backtests/{run_id}", response_model=BacktestRunOut)
def get_backtest(run_id: int, db: Session = Depends(get_db)):
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"backtest run {run_id} not found")
    return run


@router.post("/strategies/{strategy_id}/sweep", response_model=SweepOut)
def run_sweep(
    strategy_id: int,
    payload: SweepRequest,
    db: Session = Depends(get_db),
    source: CandleSource = Depends(get_candle_source),
):
    """Sweep two parameters and store the grid the topography view reads.

    Synchronous, like the single backtest, and bounded by the same reasoning —
    see ``sweep_service.MAX_SWEEP_CELLS``. A grid above that limit is refused
    with the arithmetic rather than attempted and abandoned halfway.
    """
    strategy = _get_strategy(db, strategy_id)
    try:
        return sweep_service.run_sweep(
            db,
            strategy,
            source,
            param_x=payload.param_x,
            param_y=payload.param_y,
            metric=payload.metric,
            version=payload.version,
            start=_as_utc(payload.start),
            end=_as_utc(payload.end),
            label=payload.label,
        )
    except SweepTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except StrategyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StrategyServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CandleDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
