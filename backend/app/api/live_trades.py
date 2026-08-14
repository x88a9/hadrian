"""Live-trade (ticket) endpoints (Phase 7).

A single generic ``POST /live-trades/{id}/transition`` drives the lifecycle so
there is one validation point (``ALLOWED_TRANSITIONS``). The list orders
non-terminal tickets first (newest on top), then closed, then cancelled.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.models import LiveTrade, System, Venue
from app.schemas.live_trade import (
    LiveMetricsOut,
    LiveTradeCreate,
    LiveTradeListResponse,
    LiveTradeOut,
    LiveTradeUpdate,
    TransitionRequest,
)
from app.services import live_service

router = APIRouter(tags=["live-trades"])

TERMINAL_STAGES = ("closed", "cancelled")

# from-stage -> allowed target stages
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "setup_sighted": {"risk_calculated", "cancelled"},
    "risk_calculated": {"risk_calculated", "order_placed", "cancelled"},
    "order_placed": {"entry_filled", "cancelled"},
    "entry_filled": {"running", "closed"},
    "running": {"closed"},
}

STAGE_TIMESTAMP = {
    "risk_calculated": "risk_calculated_at",
    "order_placed": "order_placed_at",
    "entry_filled": "entry_filled_at",
    "running": "running_at",
    "closed": "closed_at",
    "cancelled": "cancelled_at",
}


def _out(trade: LiveTrade) -> LiveTradeOut:
    out = LiveTradeOut.model_validate(trade)
    if trade.system is not None:
        out.system_name = trade.system.name
    return out


def _get_or_404(db: Session, live_trade_id: int) -> LiveTrade:
    trade = db.get(LiveTrade, live_trade_id)
    if trade is None:
        raise HTTPException(
            status_code=404, detail=f"live trade {live_trade_id} not found"
        )
    return trade


def _sort_key(t: LiveTrade):
    # Non-terminal first (0), then terminal (1); within, most recent first.
    is_terminal = 1 if t.stage in TERMINAL_STAGES else 0
    recency = t.closed_at or t.cancelled_at or t.created_at
    ts = recency.timestamp() if recency is not None else 0.0
    return (is_terminal, -ts)


@router.get("/live-trades", response_model=LiveTradeListResponse)
def list_live_trades(
    db: Session = Depends(get_db),
    system_id: Optional[int] = None,
    stage: Optional[str] = None,
    open_only: bool = False,
    include_cancelled: bool = True,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> LiveTradeListResponse:
    stmt = select(LiveTrade).options(joinedload(LiveTrade.system))
    if system_id is not None:
        stmt = stmt.where(LiveTrade.system_id == system_id)
    if stage is not None:
        stmt = stmt.where(LiveTrade.stage == stage)
    if open_only:
        stmt = stmt.where(LiveTrade.stage.in_(live_service.OPEN_STAGES))
    if not include_cancelled:
        stmt = stmt.where(LiveTrade.stage != "cancelled")
    if date_from is not None:
        stmt = stmt.where(LiveTrade.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(LiveTrade.created_at < date_to + timedelta(days=1))

    trades = list(db.execute(stmt).scalars().all())
    trades.sort(key=_sort_key)
    total = len(trades)
    page = trades[offset : offset + limit]
    return LiveTradeListResponse(
        total=total, limit=limit, offset=offset, items=[_out(t) for t in page]
    )


@router.get("/live-trades/metrics", response_model=LiveMetricsOut)
def get_live_metrics(
    db: Session = Depends(get_db), system_id: Optional[int] = None
) -> LiveMetricsOut:
    return LiveMetricsOut(**live_service.live_stats(db, system_id=system_id))


@router.post("/live-trades", response_model=LiveTradeOut, status_code=201)
def create_live_trade(
    body: LiveTradeCreate, db: Session = Depends(get_db)
) -> LiveTradeOut:
    # ``system_id`` is optional: a free-standing (discretionary) trade
    # soll trotzdem sauber im Live-Journal landen (Phase 8).
    system = None
    if body.system_id is not None:
        system = db.get(System, body.system_id)
        if system is None:
            raise HTTPException(
                status_code=404, detail=f"system {body.system_id} not found"
            )

    venue_id = body.venue_id
    if venue_id is None:
        v = live_service.default_venue(db)
        venue_id = v.id if v is not None else None
    elif db.get(Venue, venue_id) is None:
        raise HTTPException(status_code=404, detail=f"venue {venue_id} not found")

    portfolio = (
        body.portfolio_size
        if body.portfolio_size is not None
        else live_service.current_balance(db)
    )
    # The asset is inherited from the system unless overridden, which is what
    # resolves the correct lot size automatically. Without a system, the asset
    # comes from the request body alone.
    asset = body.asset or (system.asset if system is not None else None)
    setting = live_service.resolve_asset_setting(db, venue_id, asset)

    now = live_service.now_utc()
    trade = LiveTrade(
        system_id=system.id if system is not None else None,
        venue_id=venue_id,
        asset=asset,
        entry_order_type=body.entry_order_type,
        planned_entry=body.planned_entry,
        planned_stop=body.planned_stop,
        risk_modifier=body.risk_modifier,
        notes=body.notes,
        chart_url=body.chart_url,
        stage="setup_sighted",
        setup_sighted_at=now,
        opened_at=now,
    )
    live_service.snapshot_from_setting(trade, setting, portfolio)
    db.add(trade)
    db.flush()

    # Optional inline sizing step (new-trade flow: size first, then ticket).
    have_risk = body.desired_risk_usd is not None or body.risk_pct is not None
    if (
        body.run_risk_calc
        and body.planned_entry is not None
        and body.planned_stop is not None
        and have_risk
    ):
        live_service.store_risk(
            db,
            trade,
            desired_risk_usd=body.desired_risk_usd,
            risk_pct=body.risk_pct,
            risk_modifier=body.risk_modifier,
            portfolio_size=portfolio,
        )
        trade.stage = "risk_calculated"
        trade.risk_calculated_at = now

    db.commit()
    db.refresh(trade)
    return _out(trade)


@router.get("/live-trades/{live_trade_id}", response_model=LiveTradeOut)
def get_live_trade(live_trade_id: int, db: Session = Depends(get_db)) -> LiveTradeOut:
    return _out(_get_or_404(db, live_trade_id))


# Execution fields that must stay correctable after the fill: a mistyped
# actual_entry once got frozen in for good, which is what prompted this.
FILL_FIELDS = {"actual_entry", "actual_stop"}
# Editable on a closed trade only; before that they go through /transition.
CLOSE_FIELDS = {"exit_price", "realized_pnl_usd", "fees_paid", "funding_paid"}
FILL_STAGES = ("entry_filled", "running", "closed")


@router.patch("/live-trades/{live_trade_id}", response_model=LiveTradeOut)
def patch_live_trade(
    live_trade_id: int, body: LiveTradeUpdate, db: Session = Depends(get_db)
) -> LiveTradeOut:
    """Edit mutable fields.

    ``notes``/``chart_url``/``rules_followed`` are always editable; plan fields
    (asset/entry_order_type/planned_*) only before the order is placed;
    ``actual_entry``/``actual_stop`` only from ``entry_filled`` on; the result
    fields (exit_price/realized_pnl_usd/fees_paid/funding_paid) only on a closed
    trade. Anything else -> 409. Editing a closed trade re-derives
    realized/R/win-loss/deviation and appends a balance-correcting ledger row.
    """
    trade = _get_or_404(db, live_trade_id)
    fields = body.model_dump(exclude_unset=True)

    plan_fields = {"asset", "entry_order_type", "planned_entry", "planned_stop"}
    touching_plan = plan_fields & set(fields)
    plan_locked = trade.stage not in ("setup_sighted", "risk_calculated")
    if touching_plan and plan_locked:
        raise HTTPException(
            status_code=409,
            detail=f"plan fields are locked in stage '{trade.stage}'",
        )

    touching_fill = FILL_FIELDS & set(fields)
    if touching_fill and trade.stage not in FILL_STAGES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"execution fields {sorted(touching_fill)} are only editable "
                f"from stage 'entry_filled' on (current: '{trade.stage}')"
            ),
        )

    touching_close = CLOSE_FIELDS & set(fields)
    if touching_close and trade.stage != "closed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"result fields {sorted(touching_close)} are only editable on a "
                f"closed trade (current: '{trade.stage}')"
            ),
        )

    for key, value in fields.items():
        setattr(trade, key, value)

    if trade.stage == "closed" and (touching_fill or touching_close):
        # Price changed but no real fees supplied -> re-estimate them from the
        # snapshot, otherwise the fee share no longer matches the price.
        reestimate = bool({"exit_price", "actual_entry"} & set(fields)) and (
            "fees_paid" not in fields
        )
        live_service.recompute_close(
            db,
            trade,
            realized_override=fields.get("realized_pnl_usd"),
            reestimate_fees=reestimate,
            note=f"Korrektur Trade #{trade.id}",
        )
    elif "actual_entry" in fields and trade.planned_entry is not None:
        trade.slippage = (
            trade.actual_entry - trade.planned_entry
            if trade.actual_entry is not None
            else None
        )

    db.commit()
    db.refresh(trade)
    return _out(trade)


@router.post(
    "/live-trades/{live_trade_id}/transition", response_model=LiveTradeOut
)
def transition_live_trade(
    live_trade_id: int, body: TransitionRequest, db: Session = Depends(get_db)
) -> LiveTradeOut:
    trade = _get_or_404(db, live_trade_id)
    target = body.target_stage

    allowed = ALLOWED_TRANSITIONS.get(trade.stage, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"cannot transition from '{trade.stage}' to '{target}'",
        )

    now = live_service.now_utc()

    if target == "risk_calculated":
        try:
            live_service.store_risk(
                db,
                trade,
                planned_entry=body.planned_entry,
                planned_stop=body.planned_stop,
                desired_risk_usd=body.desired_risk_usd,
                risk_pct=body.risk_pct,
                risk_modifier=body.risk_modifier,
                portfolio_size=body.portfolio_size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        trade.stage = "risk_calculated"
        trade.risk_calculated_at = now

    elif target == "order_placed":
        if body.entry_order_type is not None:
            trade.entry_order_type = body.entry_order_type
        trade.stage = "order_placed"
        trade.order_placed_at = now

    elif target == "entry_filled":
        trade.actual_entry = (
            body.actual_entry
            if body.actual_entry is not None
            else trade.planned_entry
        )
        if body.actual_stop is not None:
            trade.actual_stop = body.actual_stop
        elif trade.actual_stop is None:
            trade.actual_stop = trade.planned_stop
        if trade.actual_entry is not None and trade.planned_entry is not None:
            trade.slippage = trade.actual_entry - trade.planned_entry
        trade.stage = "entry_filled"
        trade.entry_filled_at = now

    elif target == "running":
        trade.stage = "running"
        trade.running_at = now

    elif target == "closed":
        if body.exit_price is None and body.realized_pnl_usd is None:
            raise HTTPException(
                status_code=422,
                detail="closing requires 'exit_price' or 'realized_pnl_usd'",
            )
        # Without exit_price the explicitly reported net result (the exchange
        # statement) applies — same function, override instead of price maths.
        live_service.close_live_trade(
            db,
            trade,
            exit_price=body.exit_price,
            actual_entry=body.actual_entry,
            actual_stop=body.actual_stop,
            fees_paid=body.fees_paid,
            funding_paid=body.funding_paid,
            realized_pnl_usd=(
                body.realized_pnl_usd if body.exit_price is None else None
            ),
            rules_followed=body.rules_followed,
            closed_at=now,
        )

    elif target == "cancelled":
        trade.stage = "cancelled"
        trade.cancelled_at = now
        if body.note is not None:
            trade.notes = (
                (trade.notes + "\n" if trade.notes else "") + body.note
            )

    db.commit()
    db.refresh(trade)
    return _out(trade)


@router.delete("/live-trades/{live_trade_id}", status_code=204)
def delete_live_trade(
    live_trade_id: int, db: Session = Depends(get_db)
) -> Response:
    """Delete a trade in any stage — including a closed one.

    A wrongly recorded trade must be removable, otherwise a bad number is stuck
    in the statistics forever. To keep the balance honest, the trade's whole
    contribution is reversed first with one balancing ledger row (the ledger
    itself stays append-only). The FK is ON DELETE SET NULL, so that row loses
    its reference — the trade id therefore goes into its note.
    """
    trade = _get_or_404(db, live_trade_id)
    live_service.reverse_trade_balance(
        db,
        trade,
        change_type="trade_delete",
        note=f"reversal of trade #{trade.id}",
    )
    db.delete(trade)
    db.commit()
    return Response(status_code=204)
