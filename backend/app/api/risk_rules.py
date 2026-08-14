"""Read-only REST endpoint for risk rules (Phase 4, T4, D3).

No breach check / alerting — schema + list only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import RiskRule
from app.schemas.risk_rule import RiskRuleOut, RiskRulesResponse

router = APIRouter(tags=["risk-rules"])


@router.get("/risk-rules", response_model=RiskRulesResponse)
def list_risk_rules(db: Session = Depends(get_db)) -> RiskRulesResponse:
    rules = db.execute(select(RiskRule).order_by(RiskRule.id)).scalars().all()
    return RiskRulesResponse(items=[RiskRuleOut.model_validate(r) for r in rules])
