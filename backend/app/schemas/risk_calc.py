"""Schemas for the standalone risk calculator (Phase 7)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, model_validator


class RiskCalcRequest(BaseModel):
    """Inputs for ``POST /risk/calc``.

    Provide exactly one of ``desired_risk_usd`` / ``risk_pct``. ``portfolio_size``
    defaults server-side to the current account balance. ``venue_id`` / ``asset``
    select the fee settings (default: seeded venue + DEFAULT asset).
    """

    entry_price: float
    stop_price: float
    desired_risk_usd: Optional[float] = None
    risk_pct: Optional[float] = None
    portfolio_size: Optional[float] = None
    venue_id: Optional[int] = None
    asset: Optional[str] = None
    risk_modifier: float = 1.0

    @model_validator(mode="after")
    def _exactly_one_risk(self) -> "RiskCalcRequest":
        has_usd = self.desired_risk_usd is not None
        has_pct = self.risk_pct is not None
        if has_usd == has_pct:
            raise ValueError(
                "provide exactly one of 'desired_risk_usd' or 'risk_pct'"
            )
        return self


class RiskCalcResponse(BaseModel):
    direction: str
    price_move: float
    effective_desired_risk: float
    portfolio_size: float
    risk_pct: float
    initial_pos_size: float
    initial_notional: float
    initial_fees: float
    initial_exp_loss: float
    adjusted_pos_size: float
    adjusted_notional: float
    adjusted_fees: float
    adjusted_exp_loss: float
    adjusted_risk: float
    valid_risk: bool
    risk_lower_bound: float
    risk_upper_bound: float
    # Leverage required by the calculation, buffer included.
    leverage: float
    # Verwendete Fee-Settings (transparent).
    entry_fee_pct: float
    exit_fee_pct: float
    # The asset-specific lot size the position was rounded to.
    min_position_size: float
    # --- Leverage concepts kept separate, plus exchange limits --- #
    implicit_leverage: float
    exchange_leverage: Optional[float] = None
    max_leverage: Optional[float] = None
    leverage_exceeds_max: bool = False
    risk_overshoot_pct: float = 0.0
    floor_pos_size: float = 0.0
    floor_risk: float = 0.0
    floor_valid: bool = False
    rounds_to_zero: bool = False
    min_order_value_usd: Optional[float] = None
    below_min_order_value: bool = False
    # Which asset applied, and whether real settings existed for it.
    asset: Optional[str] = None
    settings_asset: Optional[str] = None
    settings_fallback: bool = False
