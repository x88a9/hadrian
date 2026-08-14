"""REST endpoints for trading systems (API contract §1).

Metrics are computed on the fly (see docs/DECISIONS.md, "Metric formulas").
``GET /systems``
loads every trade exactly once and groups them in Python (no N+1 queries).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models import Concept, LiveTrade, System, SystemConcept, Trade
from app.schemas.metrics import MetricsTriple
from app.schemas.report import (
    ReportConcept,
    SystemReport,
    TradesSummary,
)
from app.schemas.system import (
    SystemCreate,
    SystemDetail,
    SystemSummary,
    SystemsResponse,
    SystemUpdate,
)
from app.services.import_service import split_name
from app.services.metrics import compute_all

router = APIRouter(tags=["systems"])

# Fields whose UI edits survive a re-import (docs/DECISIONS.md, "Re-import
# protection").
OVERRIDABLE_FIELDS = ("entry_rule", "sl_rule", "tp_rule", "notes", "timeframe", "asset")


def _metrics_triple(trades, split_date) -> MetricsTriple:
    return MetricsTriple.model_validate(compute_all(trades, split_date))


def _detail(system: System) -> SystemDetail:
    split_date = settings.IS_OOS_SPLIT_DATE
    return SystemDetail(
        id=system.id,
        name=system.name,
        prefix=system.prefix,
        timeframe=system.timeframe,
        asset=system.asset,
        status=system.status,
        import_status=system.import_status,
        provenance=system.provenance,
        source_engine=system.source_engine,
        origin=system.origin,
        entry_rule=system.entry_rule,
        sl_rule=system.sl_rule,
        tp_rule=system.tp_rule,
        notes=system.notes,
        reported_metrics=system.reported_metrics,
        user_overrides=list(system.user_overrides or []),
        split_date=split_date,
        metrics=_metrics_triple(list(system.trades), split_date),
    )


@router.get("/systems", response_model=SystemsResponse)
def list_systems(
    provenance: Optional[Literal["manual", "programmatic"]] = Query(default=None),
    db: Session = Depends(get_db),
) -> SystemsResponse:
    split_date = settings.IS_OOS_SPLIT_DATE

    stmt = select(System).order_by(System.name)
    if provenance is not None:
        stmt = stmt.where(System.provenance == provenance)
    systems = db.execute(stmt).scalars().all()

    # Load all trades once, group in Python -> no per-system query.
    trades_by_system: dict[int, list[Trade]] = defaultdict(list)
    for trade in db.execute(select(Trade)).scalars():
        trades_by_system[trade.system_id].append(trade)

    items = [
        SystemSummary(
            id=s.id,
            name=s.name,
            prefix=s.prefix,
            timeframe=s.timeframe,
            asset=s.asset,
            status=s.status,
            import_status=s.import_status,
            provenance=s.provenance,
            source_engine=s.source_engine,
            origin=s.origin,
            metrics=_metrics_triple(trades_by_system.get(s.id, []), split_date),
        )
        for s in systems
    ]
    return SystemsResponse(split_date=split_date, items=items)


@router.post("/systems", response_model=SystemDetail)
def upsert_system(
    body: SystemCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> SystemDetail:
    """Idempotent upsert of a system by ``name`` (D1).

    New system -> 201; existing name -> 200 with a partial update (only the
    fields explicitly present in the request body are applied). ``prefix`` and
    ``timeframe`` are always derived server-side from the name; client-created
    systems are marked ``import_status='complete'``.
    """
    existing = db.execute(
        select(System).where(System.name == body.name)
    ).scalar_one_or_none()

    # Explicitly set fields only (partial update semantics on the second POST).
    fields = body.model_dump(exclude_unset=True)
    fields.pop("name", None)

    if existing is None:
        prefix, timeframe = split_name(body.name)
        system = System(
            name=body.name,
            prefix=prefix,
            timeframe=timeframe,
            import_status="complete",
            origin="ui",  # created in the UI -> importers skip it entirely
        )
        for key, value in fields.items():
            setattr(system, key, value)
        db.add(system)
        response.status_code = 201
    else:
        system = existing
        for key, value in fields.items():
            setattr(system, key, value)
        # Keep prefix/timeframe in sync with the (immutable) name.
        system.prefix, system.timeframe = split_name(system.name)
        # Track explicitly set overridable fields as user_overrides. Assign a
        # new list so SQLAlchemy notices the change.
        touched = [f for f in OVERRIDABLE_FIELDS if f in fields]
        if touched:
            merged = list(system.user_overrides or [])
            for f in touched:
                if f not in merged:
                    merged.append(f)
            system.user_overrides = merged
        response.status_code = 200

    db.commit()
    db.refresh(system)
    return _detail(system)


def _get_system_or_404(db: Session, system_id: int) -> System:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail=f"system {system_id} not found")
    return system


@router.get("/systems/{system_id}", response_model=SystemDetail)
def get_system(system_id: int, db: Session = Depends(get_db)) -> SystemDetail:
    return _detail(_get_system_or_404(db, system_id))


@router.patch("/systems/{system_id}", response_model=SystemDetail)
def patch_system(
    system_id: int,
    body: SystemUpdate,
    db: Session = Depends(get_db),
) -> SystemDetail:
    """Partial update of a system (D5).

    Only explicitly set fields are applied (``exclude_unset``). ``name`` is
    immutable and ``prefix`` stays server-derived. Explicitly set fields from
    ``OVERRIDABLE_FIELDS`` are tracked in ``user_overrides`` (new list assigned
    so SQLAlchemy detects the change). An empty body is a 200 no-op.
    """
    system = _get_system_or_404(db, system_id)
    fields = body.model_dump(exclude_unset=True)

    for key, value in fields.items():
        setattr(system, key, value)

    touched = [f for f in OVERRIDABLE_FIELDS if f in fields]
    if touched:
        merged = list(system.user_overrides or [])
        for f in touched:
            if f not in merged:
                merged.append(f)
        system.user_overrides = merged

    db.commit()
    db.refresh(system)
    return _detail(system)


@router.delete("/systems/{system_id}", status_code=204)
def delete_system(system_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a system (D3). DB cascades trades / parameter_sweeps /
    system_concepts (CASCADE) and nulls journal_entries / risk_rules (SET NULL).

    Live trades are RESTRICT (Phase 7): a system with real, non-reproducible
    live tickets cannot be silently cascaded away — reject with 409 so the user
    resolves the tickets first.
    """
    system = _get_system_or_404(db, system_id)
    live_count = db.execute(
        select(func.count())
        .select_from(LiveTrade)
        .where(LiveTrade.system_id == system_id)
    ).scalar_one()
    if live_count:
        raise HTTPException(
            status_code=409,
            detail=(
                f"system has {live_count} live trade(s); delete or resolve them "
                "before deleting the system"
            ),
        )
    db.delete(system)
    db.commit()
    return Response(status_code=204)


def _trades_summary(trades: list[Trade]) -> TradesSummary:
    long_count = sum(1 for t in trades if t.direction == "long")
    short_count = sum(1 for t in trades if t.direction == "short")
    r_values = [t.r_value for t in trades if t.r_value is not None]
    dated = sorted(
        (t for t in trades if t.trade_datetime is not None),
        key=lambda t: t.trade_datetime,
    )
    undated_count = sum(1 for t in trades if t.trade_datetime is None)
    return TradesSummary(
        total=len(trades),
        long_count=long_count,
        short_count=short_count,
        best_r=max(r_values) if r_values else None,
        worst_r=min(r_values) if r_values else None,
        first_trade_at=dated[0].trade_datetime if dated else None,
        last_trade_at=dated[-1].trade_datetime if dated else None,
        undated_count=undated_count,
    )


@router.get("/systems/{system_id}/report", response_model=SystemReport)
def get_system_report(
    system_id: int, db: Session = Depends(get_db)
) -> SystemReport:
    """Report stub (D5): JSON aggregate of a system, its concepts and a trade
    summary. A later consumer renders this into a PDF; no PDF renderer is a
    dependency here.
    """
    system = _get_system_or_404(db, system_id)

    concepts = (
        db.execute(
            select(Concept)
            .join(SystemConcept, SystemConcept.concept_id == Concept.id)
            .where(SystemConcept.system_id == system_id)
            .order_by(Concept.name)
        )
        .scalars()
        .all()
    )

    return SystemReport(
        report_version=1,
        generated_at=datetime.now(timezone.utc),
        system=_detail(system),
        concepts=[ReportConcept(id=c.id, name=c.name) for c in concepts],
        trades_summary=_trades_summary(list(system.trades)),
    )
