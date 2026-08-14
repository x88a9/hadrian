"""Pydantic schemas for the metric payloads (API contract §1).

``MetricsBlock`` mirrors the 18-key dict produced by
``app.services.metrics.compute_metrics`` 1:1. ``MetricsTriple`` wraps the
all/is/oos result of ``compute_all``. Note that ``is`` is a Python keyword, so
the field is declared as ``is_`` with the alias ``"is"`` — FastAPI serializes
responses with ``by_alias=True`` by default, so the wire key is ``"is"``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MetricsBlock(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate: Optional[float] = None
    ev: Optional[float] = None
    total_r: Optional[float] = None
    avg_win_r: Optional[float] = None
    avg_loss_r: Optional[float] = None
    ece: Optional[float] = None
    evol: Optional[float] = None
    composite_score: Optional[float] = None
    composite_grade: Optional[str] = None
    ev_grade: Optional[str] = None
    ece_grade: Optional[str] = None
    evol_grade: Optional[str] = None
    first_trade_at: Optional[datetime] = None
    last_trade_at: Optional[datetime] = None
    span_days: Optional[float] = None
    # Phase-3 additive metrics (all nullable).
    profit_factor: Optional[float] = None
    max_drawdown_r: Optional[float] = None
    romad: Optional[float] = None
    skewness: Optional[float] = None
    r_p05: Optional[float] = None
    r_p25: Optional[float] = None
    r_p50: Optional[float] = None
    r_p75: Optional[float] = None
    r_p95: Optional[float] = None


class MetricsTriple(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    all: MetricsBlock
    is_: MetricsBlock = Field(alias="is")
    oos: MetricsBlock
