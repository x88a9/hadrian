"""Pydantic schemas for the /systems endpoints (API contract §1)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.schemas.metrics import MetricsTriple


class SystemSummary(BaseModel):
    id: int
    name: str
    prefix: Optional[str] = None
    timeframe: Optional[str] = None
    # The asset the system was backtested on.
    asset: Optional[str] = None
    status: str
    import_status: str
    provenance: str
    source_engine: Optional[str] = None
    # Anlage-Kanal (Phase 6, D1): 'import' | 'ui'.
    origin: str = "import"
    metrics: MetricsTriple


class SystemDetail(SystemSummary):
    entry_rule: Optional[str] = None
    sl_rule: Optional[str] = None
    tp_rule: Optional[str] = None
    notes: Optional[str] = None
    # Raw header values captured at import time; pass-through, fields nullable.
    reported_metrics: Optional[dict[str, Any]] = None
    # Field names overridden in the UI; protected against re-import.
    user_overrides: list[str] = []
    # IS/OOS split date used for the metrics triple (for the OOS line in the UI).
    split_date: date


class SystemsResponse(BaseModel):
    split_date: date
    items: list[SystemSummary]


class SystemUpdate(BaseModel):
    """Partial update payload for ``PATCH /systems/{id}`` (Phase 6, D5).

    All fields optional; the router uses ``model_dump(exclude_unset=True)``.
    ``name`` is not patchable and ``prefix`` stays server-derived from the name.
    An invalid ``status`` still yields 422 (Literal). Explicitly set fields from
    ``{entry_rule, sl_rule, tp_rule, notes, timeframe}`` are tracked in
    ``user_overrides``.
    """

    status: Optional[Literal["backtest", "live_testing", "active", "retired"]] = None
    entry_rule: Optional[str] = None
    sl_rule: Optional[str] = None
    tp_rule: Optional[str] = None
    notes: Optional[str] = None
    timeframe: Optional[str] = None
    asset: Optional[str] = None


class SystemCreate(BaseModel):
    """Upsert payload for ``POST /systems`` (Phase 2, D1).

    Only ``name`` is required. On update only explicitly set fields are applied
    (the router uses ``model_dump(exclude_unset=True)``).
    """

    name: str
    entry_rule: Optional[str] = None
    sl_rule: Optional[str] = None
    tp_rule: Optional[str] = None
    notes: Optional[str] = None
    asset: Optional[str] = None
    status: Optional[Literal["backtest", "live_testing", "active", "retired"]] = None
