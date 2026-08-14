"""Schemas for live trades / tickets (Phase 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class LiveTradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # None = free-standing trade with no system (discretionary).
    system_id: Optional[int] = None
    system_name: Optional[str] = None
    venue_id: Optional[int] = None
    asset_setting_id: Optional[int] = None
    asset: Optional[str] = None
    stage: str
    direction: Optional[str] = None
    entry_order_type: Optional[str] = None

    planned_entry: Optional[float] = None
    planned_stop: Optional[float] = None
    actual_entry: Optional[float] = None
    actual_stop: Optional[float] = None
    exit_price: Optional[float] = None

    position_size_coins: Optional[float] = None
    position_size_notional: Optional[float] = None
    leverage: Optional[float] = None
    implicit_leverage: Optional[float] = None
    exchange_leverage: Optional[float] = None
    risk_usd: Optional[float] = None
    risk_pct: Optional[float] = None
    risk_modifier: Optional[float] = None
    expected_loss: Optional[float] = None

    realized_pnl_usd: Optional[float] = None
    r_value: Optional[float] = None
    win_loss: Optional[str] = None
    deviation_pct: Optional[float] = None
    fees_paid: Optional[float] = None
    funding_paid: Optional[float] = None
    slippage: Optional[float] = None
    balance_after: Optional[float] = None

    # Fee-Snapshot (bei Anlage eingefroren).
    portfolio_size_at_creation: Optional[float] = None
    snap_entry_fee_pct: Optional[float] = None
    snap_exit_fee_pct: Optional[float] = None
    snap_min_position_size: Optional[float] = None
    snap_leverage_buffer: Optional[float] = None
    snap_upside_deviation_allowed_pct: Optional[float] = None
    snap_downside_deviation_allowed_pct: Optional[float] = None
    snap_max_leverage: Optional[float] = None
    snap_leverage_step: Optional[float] = None
    snap_min_order_value_usd: Optional[float] = None

    opened_at: Optional[datetime] = None
    setup_sighted_at: Optional[datetime] = None
    risk_calculated_at: Optional[datetime] = None
    order_placed_at: Optional[datetime] = None
    entry_filled_at: Optional[datetime] = None
    running_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    rules_followed: Optional[bool] = None
    chart_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LiveTradeCreate(BaseModel):
    """Create a ticket (stage ``setup_sighted``).

    The fee snapshot is taken here. Provide at most one of
    ``desired_risk_usd`` / ``risk_pct``. When ``run_risk_calc`` is true (default)
    and entry/stop/risk are all present, the risk stage runs immediately and the
    ticket lands in ``risk_calculated``.

    ``system_id`` may be omitted (a free-standing trade): no system is looked
    up and the asset comes from ``asset`` alone.
    """

    system_id: Optional[int] = None
    venue_id: Optional[int] = None
    asset: Optional[str] = None
    entry_order_type: Optional[Literal["market", "limit"]] = None
    planned_entry: Optional[float] = None
    planned_stop: Optional[float] = None
    desired_risk_usd: Optional[float] = None
    risk_pct: Optional[float] = None
    risk_modifier: float = 1.0
    portfolio_size: Optional[float] = None
    notes: Optional[str] = None
    chart_url: Optional[str] = None
    run_risk_calc: bool = True

    @model_validator(mode="after")
    def _at_most_one_risk(self) -> "LiveTradeCreate":
        if self.desired_risk_usd is not None and self.risk_pct is not None:
            raise ValueError(
                "provide at most one of 'desired_risk_usd' or 'risk_pct'"
            )
        return self


class LiveTradeUpdate(BaseModel):
    """Edit mutable fields.

    Stufen-Sperren setzt der Router durch (409):
    - Plan-Felder (asset/entry_order_type/planned_*): nur vor ``order_placed``.
    - Execution (actual_entry/actual_stop): from ``entry_filled`` onwards,
      closed included.
    - Ergebnis (exit_price/realized_pnl_usd/fees_paid/funding_paid): nur ``closed``.
    - notes/chart_url/rules_followed: immer.
    """

    asset: Optional[str] = None
    entry_order_type: Optional[Literal["market", "limit"]] = None
    planned_entry: Optional[float] = None
    planned_stop: Optional[float] = None
    # Execution correction: a mistyped fill has to remain repairable.
    actual_entry: Optional[float] = None
    actual_stop: Optional[float] = None
    exit_price: Optional[float] = None
    realized_pnl_usd: Optional[float] = None
    fees_paid: Optional[float] = None
    funding_paid: Optional[float] = None
    chart_url: Optional[str] = None
    rules_followed: Optional[bool] = None
    notes: Optional[str] = None


TARGET_STAGES = Literal[
    "risk_calculated",
    "order_placed",
    "entry_filled",
    "running",
    "closed",
    "cancelled",
]


class TransitionRequest(BaseModel):
    """Move a ticket to ``target_stage`` with the fields that stage needs.

    - risk_calculated: planned_entry/stop + desired_risk_usd|risk_pct (or already on ticket)
    - order_placed: entry_order_type (optional)
    - entry_filled: actual_entry (default = planned_entry), actual_stop (optional)
    - running: —
    - closed: exit_price (or explicit realized_pnl_usd) + optional fees_paid/funding_paid
    - cancelled: — (only before entry_filled)
    """

    target_stage: TARGET_STAGES
    # risk stage
    planned_entry: Optional[float] = None
    planned_stop: Optional[float] = None
    desired_risk_usd: Optional[float] = None
    risk_pct: Optional[float] = None
    risk_modifier: Optional[float] = None
    portfolio_size: Optional[float] = None
    # order stage
    entry_order_type: Optional[Literal["market", "limit"]] = None
    # fill stage
    actual_entry: Optional[float] = None
    actual_stop: Optional[float] = None
    # close stage
    exit_price: Optional[float] = None
    realized_pnl_usd: Optional[float] = None
    fees_paid: Optional[float] = None
    funding_paid: Optional[float] = None
    rules_followed: Optional[bool] = None
    note: Optional[str] = None


class LiveTradeListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[LiveTradeOut]


class LiveMetricsOut(BaseModel):
    closed_count: int
    open_count: int
    total_pnl_usd: float
    total_r: float
    wins: int
    losses: int
    win_rate: Optional[float] = None
    avg_deviation_pct: Optional[float] = None
    current_balance: float
