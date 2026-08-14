"""Standalone risk calculator endpoint.

Usable without creating a ticket. Reproduces the verified reference cases
through the seeded asset settings (see tests/integration/test_risk_endpoint.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.risk_calc import RiskCalcRequest, RiskCalcResponse
from app.services import live_service
from app.services.risk_calc import compute_risk

router = APIRouter(tags=["risk"])


@router.post("/risk/calc", response_model=RiskCalcResponse)
def calc_risk(body: RiskCalcRequest, db: Session = Depends(get_db)) -> RiskCalcResponse:
    portfolio = (
        body.portfolio_size
        if body.portfolio_size is not None
        else live_service.current_balance(db)
    )
    if portfolio <= 0:
        raise HTTPException(
            status_code=422,
            detail="portfolio_size must be positive (set an account balance)",
        )

    if body.desired_risk_usd is not None:
        desired = body.desired_risk_usd
    else:
        desired = portfolio * (body.risk_pct or 0.0) / 100.0

    setting = live_service.resolve_asset_setting(db, body.venue_id, body.asset)
    inp = live_service.inputs_from_setting(
        setting,
        entry_price=body.entry_price,
        stop_price=body.stop_price,
        desired_risk_usd=desired,
        portfolio_size=portfolio,
        risk_modifier=body.risk_modifier,
    )
    result = compute_risk(inp)
    risk_pct = (
        result.effective_desired_risk / portfolio * 100.0 if portfolio else 0.0
    )
    return RiskCalcResponse(
        **result.as_dict(),
        portfolio_size=portfolio,
        risk_pct=risk_pct,
        entry_fee_pct=inp.entry_fee_pct,
        exit_fee_pct=inp.exit_fee_pct,
        asset=body.asset,
        settings_asset=setting.asset if setting is not None else None,
        settings_fallback=live_service.is_fallback_setting(setting, body.asset),
    )
