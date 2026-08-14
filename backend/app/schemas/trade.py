"""Pydantic schemas for the /trades endpoint (API contract §1).

All trade fields except ``id``, ``system_id``, ``system_name`` and ``source``
are nullable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    system_id: int
    system_name: str
    trade_datetime: Optional[datetime] = None
    zone: Optional[str] = None
    timeframe: Optional[str] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    exit: Optional[float] = None
    direction: Optional[str] = None
    r_value: Optional[float] = None
    win_loss: Optional[str] = None
    source: str


class TradeListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TradeOut]


class TradeCreate(BaseModel):
    """Payload for ``POST /trades`` (Phase 2, D1).

    Exactly one of ``system_id`` / ``system_name`` must be provided. All trade
    fields are optional; ``source`` is set server-side to ``'auto'`` and is not
    part of this schema. When ``win_loss`` is omitted it is derived from
    ``r_value`` (see ``derive_win_loss``).
    """

    system_id: Optional[int] = None
    system_name: Optional[str] = None
    trade_datetime: Optional[datetime] = None
    zone: Optional[str] = None
    timeframe: Optional[str] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    exit: Optional[float] = None
    direction: Optional[Literal["long", "short"]] = None
    r_value: Optional[float] = None
    win_loss: Optional[Literal["win", "loss", "draw"]] = None
    # How the trade was created. The 'auto' default preserves the existing
    # client/ingest contract; 'ui' is safe against re-import. 'manual' is
    # deliberately not selectable (Literal -> 422) and stays reserved for
    # xlsx trades.
    source: Literal["auto", "ui"] = "auto"

    @model_validator(mode="after")
    def _exactly_one_system_ref(self) -> "TradeCreate":
        has_id = self.system_id is not None
        has_name = self.system_name is not None
        if has_id == has_name:
            raise ValueError(
                "exactly one of 'system_id' or 'system_name' must be provided"
            )
        return self


class TradeUpdate(BaseModel):
    """Partial update payload for ``PATCH /trades/{id}`` (Phase 6, D4).

    All trade fields are optional; the router uses ``model_dump(exclude_unset=True)``.
    ``system_id`` and ``source`` are immutable (not part of this schema). When
    ``r_value`` is set without an explicit ``win_loss``, ``win_loss`` is re-derived
    via ``derive_win_loss``.
    """

    trade_datetime: Optional[datetime] = None
    zone: Optional[str] = None
    timeframe: Optional[str] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    exit: Optional[float] = None
    direction: Optional[Literal["long", "short"]] = None
    r_value: Optional[float] = None
    win_loss: Optional[Literal["win", "loss", "draw"]] = None
