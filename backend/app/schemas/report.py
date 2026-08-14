"""Pydantic schemas for the system report stub (Phase 4, T5, D5).

JSON-only stub. A later consumer renders this into a PDF; no PDF renderer is
pulled in as a dependency here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.system import SystemDetail


class ReportConcept(BaseModel):
    id: int
    name: str


class TradesSummary(BaseModel):
    total: int
    long_count: int
    short_count: int
    best_r: Optional[float] = None
    worst_r: Optional[float] = None
    first_trade_at: Optional[datetime] = None
    last_trade_at: Optional[datetime] = None
    undated_count: int


class SystemReport(BaseModel):
    report_version: int
    generated_at: datetime
    system: SystemDetail
    concepts: list[ReportConcept]
    trades_summary: TradesSummary
