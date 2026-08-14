"""Pydantic schemas for the /risk-rules endpoint (Phase 4, T4)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RiskRuleOut(BaseModel):
    id: int
    name: str
    system_id: Optional[int] = None
    max_daily_r: Optional[float] = None
    max_weekly_r: Optional[float] = None
    max_monthly_r: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    active: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class RiskRulesResponse(BaseModel):
    items: list[RiskRuleOut]
