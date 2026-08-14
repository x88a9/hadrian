"""REST endpoint for the trade explorer (API contract §1).

Server-side filtering + pagination. ``date_to`` is a calendar date interpreted
inclusively (up to end of day), i.e. ``trade_datetime < date_to + 1 day``.
Ordering is by ``trade_datetime`` (NULLS LAST), then ``id``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.models import System, Trade
from app.schemas.trade import (
    TradeCreate,
    TradeListResponse,
    TradeOut,
    TradeUpdate,
)
from app.services.metrics import derive_win_loss

router = APIRouter(tags=["trades"])


def _trade_out(trade: Trade, system_name: str) -> TradeOut:
    return TradeOut(
        id=trade.id,
        system_id=trade.system_id,
        system_name=system_name,
        trade_datetime=trade.trade_datetime,
        zone=trade.zone,
        timeframe=trade.timeframe,
        entry=trade.entry,
        sl=trade.sl,
        exit=trade.exit,
        direction=trade.direction,
        r_value=trade.r_value,
        win_loss=trade.win_loss,
        source=trade.source,
    )


@router.get("/trades", response_model=TradeListResponse)
def list_trades(
    db: Session = Depends(get_db),
    system_id: Optional[int] = None,
    direction: Optional[Literal["long", "short"]] = None,
    win_loss: Optional[Literal["win", "loss", "draw"]] = None,
    source: Optional[Literal["manual", "auto", "ui"]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    order: Literal["asc", "desc"] = "asc",
) -> TradeListResponse:
    filters = []
    if system_id is not None:
        filters.append(Trade.system_id == system_id)
    if direction is not None:
        filters.append(Trade.direction == direction)
    if win_loss is not None:
        filters.append(Trade.win_loss == win_loss)
    if source is not None:
        filters.append(Trade.source == source)
    if date_from is not None:
        filters.append(Trade.trade_datetime >= date_from)
    if date_to is not None:
        filters.append(Trade.trade_datetime < date_to + timedelta(days=1))

    total = db.execute(
        select(func.count()).select_from(Trade).where(*filters)
    ).scalar_one()

    dt_order = (
        Trade.trade_datetime.desc()
        if order == "desc"
        else Trade.trade_datetime.asc()
    )
    stmt = (
        select(Trade)
        .options(joinedload(Trade.system))
        .where(*filters)
        .order_by(dt_order.nulls_last(), Trade.id.asc())
        .limit(limit)
        .offset(offset)
    )
    trades = db.execute(stmt).scalars().all()

    items = [
        TradeOut(
            id=t.id,
            system_id=t.system_id,
            system_name=t.system.name,
            trade_datetime=t.trade_datetime,
            zone=t.zone,
            timeframe=t.timeframe,
            entry=t.entry,
            sl=t.sl,
            exit=t.exit,
            direction=t.direction,
            r_value=t.r_value,
            win_loss=t.win_loss,
            source=t.source,
        )
        for t in trades
    ]
    return TradeListResponse(total=total, limit=limit, offset=offset, items=items)


@router.post("/trades", response_model=TradeOut, status_code=201)
def create_trade(body: TradeCreate, db: Session = Depends(get_db)) -> TradeOut:
    """Log a single trade (D1/D2).

    ``source`` comes from the body (default ``'auto'`` for client compatibility;
    ``'ui'`` is re-import-safe; ``'manual'`` is not selectable). The system is
    resolved by ``system_id`` or ``system_name`` (exactly one, enforced by the
    schema); an unknown system yields 404. A missing ``win_loss`` is derived from
    ``r_value``.
    """
    if body.system_id is not None:
        system = db.get(System, body.system_id)
        if system is None:
            raise HTTPException(
                status_code=404, detail=f"system {body.system_id} not found"
            )
    else:
        system = db.execute(
            select(System).where(System.name == body.system_name)
        ).scalar_one_or_none()
        if system is None:
            raise HTTPException(
                status_code=404, detail=f"system '{body.system_name}' not found"
            )

    win_loss = body.win_loss if body.win_loss is not None else derive_win_loss(body.r_value)

    trade = Trade(
        system_id=system.id,
        trade_datetime=body.trade_datetime,
        zone=body.zone,
        timeframe=body.timeframe,
        entry=body.entry,
        sl=body.sl,
        exit=body.exit,
        direction=body.direction,
        r_value=body.r_value,
        win_loss=win_loss,
        source=body.source,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)

    return _trade_out(trade, system.name)


@router.patch("/trades/{trade_id}", response_model=TradeOut)
def patch_trade(
    trade_id: int, body: TradeUpdate, db: Session = Depends(get_db)
) -> TradeOut:
    """Partial update of a trade (D4).

    Only explicitly set fields are applied (``exclude_unset``). ``system_id`` and
    ``source`` are immutable. When ``r_value`` is set without an explicit
    ``win_loss``, ``win_loss`` is re-derived via ``derive_win_loss``.
    """
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")

    fields = body.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(trade, key, value)

    if "r_value" in fields and "win_loss" not in fields:
        trade.win_loss = derive_win_loss(trade.r_value)

    db.commit()
    db.refresh(trade)
    return _trade_out(trade, trade.system.name)


@router.delete("/trades/{trade_id}", status_code=204)
def delete_trade(trade_id: int, db: Session = Depends(get_db)) -> Response:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")
    db.delete(trade)
    db.commit()
    return Response(status_code=204)
