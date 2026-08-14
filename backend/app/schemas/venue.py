"""Schemas for venues and versioned asset settings (Phase 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AssetSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    venue_id: int
    asset: str
    entry_fee_pct: float
    exit_fee_pct: float
    min_position_size: float
    max_leverage: Optional[float] = None
    leverage_step: float = 1.0
    min_order_value_usd: Optional[float] = None
    leverage_buffer: float
    upside_deviation_allowed_pct: float
    downside_deviation_allowed_pct: float
    valid_from: datetime
    created_at: datetime


class AssetSettingCreate(BaseModel):
    """Create a NEW settings version (never mutates an existing one).

    ``valid_from`` defaults to now server-side. Old live trades keep their
    snapshot and are unaffected.
    """

    asset: str = "DEFAULT"
    entry_fee_pct: float
    exit_fee_pct: float
    min_position_size: float
    max_leverage: Optional[float] = None
    leverage_step: float = 1.0
    min_order_value_usd: Optional[float] = 10.0
    leverage_buffer: float = 0.1
    upside_deviation_allowed_pct: float = 0.05
    downside_deviation_allowed_pct: float = 0.05
    valid_from: Optional[datetime] = None


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    notes: Optional[str] = None
    created_at: datetime
    current_settings: Optional[AssetSettingOut] = None


class VenueCreate(BaseModel):
    name: str
    notes: Optional[str] = None


class VenuesResponse(BaseModel):
    items: list[VenueOut]
