"""Venue / asset-settings / account-balance endpoints (Phase 7).

Asset settings are append-only versioned: a fee change POSTs a new version and
never mutates an old one (that is what keeps historic live trades isolated). The
balance is an append-only ledger; a correction posts a new absolute row.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountBalance, AssetSetting, Venue
from app.core.db import get_db
from app.schemas.account import (
    AccountBalanceOut,
    AccountBalanceResponse,
    BalanceCorrection,
)
from app.schemas.venue import (
    AssetSettingCreate,
    AssetSettingOut,
    VenueCreate,
    VenueOut,
    VenuesResponse,
)
from app.services import live_service

router = APIRouter(tags=["live-settings"])


def _venue_out(db: Session, venue: Venue) -> VenueOut:
    current = live_service.resolve_asset_setting(db, venue.id, None)
    out = VenueOut.model_validate(venue)
    out.current_settings = (
        AssetSettingOut.model_validate(current) if current is not None else None
    )
    return out


@router.get("/venues", response_model=VenuesResponse)
def list_venues(db: Session = Depends(get_db)) -> VenuesResponse:
    venues = db.execute(select(Venue).order_by(Venue.id)).scalars().all()
    return VenuesResponse(items=[_venue_out(db, v) for v in venues])


@router.post("/venues", response_model=VenueOut, status_code=201)
def create_venue(body: VenueCreate, db: Session = Depends(get_db)) -> VenueOut:
    existing = db.execute(
        select(Venue).where(Venue.name == body.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"venue '{body.name}' exists")
    venue = Venue(name=body.name, notes=body.notes)
    db.add(venue)
    db.commit()
    db.refresh(venue)
    return _venue_out(db, venue)


@router.patch("/venues/{venue_id}", response_model=VenueOut)
def patch_venue(
    venue_id: int, body: VenueCreate, db: Session = Depends(get_db)
) -> VenueOut:
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail=f"venue {venue_id} not found")
    venue.name = body.name
    venue.notes = body.notes
    db.commit()
    db.refresh(venue)
    return _venue_out(db, venue)


@router.get("/asset-settings", response_model=list[AssetSettingOut])
def list_asset_settings(
    db: Session = Depends(get_db),
    venue_id: Optional[int] = None,
    asset: Optional[str] = None,
    current: bool = Query(False),
) -> list[AssetSettingOut]:
    if current:
        setting = live_service.resolve_asset_setting(db, venue_id, asset)
        return [AssetSettingOut.model_validate(setting)] if setting else []
    stmt = select(AssetSetting)
    if venue_id is not None:
        stmt = stmt.where(AssetSetting.venue_id == venue_id)
    if asset is not None:
        stmt = stmt.where(AssetSetting.asset == asset)
    stmt = stmt.order_by(AssetSetting.valid_from.desc(), AssetSetting.id.desc())
    rows = db.execute(stmt).scalars().all()
    return [AssetSettingOut.model_validate(r) for r in rows]


@router.post(
    "/venues/{venue_id}/asset-settings",
    response_model=AssetSettingOut,
    status_code=201,
)
def create_asset_setting(
    venue_id: int, body: AssetSettingCreate, db: Session = Depends(get_db)
) -> AssetSettingOut:
    """Create a NEW settings version. Never mutates an existing one — historic
    live trades keep their snapshot and are unaffected."""
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail=f"venue {venue_id} not found")
    setting = AssetSetting(
        venue_id=venue_id,
        asset=body.asset,
        entry_fee_pct=body.entry_fee_pct,
        exit_fee_pct=body.exit_fee_pct,
        min_position_size=body.min_position_size,
        leverage_buffer=body.leverage_buffer,
        upside_deviation_allowed_pct=body.upside_deviation_allowed_pct,
        downside_deviation_allowed_pct=body.downside_deviation_allowed_pct,
    )
    if body.valid_from is not None:
        setting.valid_from = body.valid_from
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return AssetSettingOut.model_validate(setting)


@router.get("/account/balance", response_model=AccountBalanceResponse)
def get_balance(
    db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=1000)
) -> AccountBalanceResponse:
    rows = (
        db.execute(
            select(AccountBalance)
            .order_by(AccountBalance.as_of.desc(), AccountBalance.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return AccountBalanceResponse(
        current_balance=live_service.current_balance(db),
        history=[AccountBalanceOut.model_validate(r) for r in rows],
    )


@router.post("/account/balance", response_model=AccountBalanceOut, status_code=201)
def correct_balance(
    body: BalanceCorrection, db: Session = Depends(get_db)
) -> AccountBalanceOut:
    """Post a manual absolute correction (append-only)."""
    prev = live_service.current_balance(db)
    row = live_service.append_balance(
        db,
        balance=body.balance,
        change_type="manual",
        delta=body.balance - prev,
        note=body.note,
    )
    db.commit()
    db.refresh(row)
    return AccountBalanceOut.model_validate(row)
