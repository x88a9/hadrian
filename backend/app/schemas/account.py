"""Schemas for the account balance ledger (Phase 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    balance: float
    delta: Optional[float] = None
    change_type: str
    live_trade_id: Optional[int] = None
    note: Optional[str] = None
    as_of: datetime
    created_at: datetime


class AccountBalanceResponse(BaseModel):
    current_balance: float
    history: list[AccountBalanceOut]


class BalanceCorrection(BaseModel):
    """A manual absolute correction of the current balance (append-only)."""

    balance: float
    note: Optional[str] = None
