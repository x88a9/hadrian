from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ParameterSweep(Base):
    """A stored parameter-sweep grid for a system (Phase 3 — model only).

    ``points`` holds the raw grid as JSONB (generic x/y/metric axes); no
    endpoint, schema or UI exists yet. Axis names are configurable so the same
    table serves e.g. tp_r x sl_r heatmaps keyed on any metric.
    """

    __tablename__ = "parameter_sweeps"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[int] = mapped_column(
        ForeignKey("systems.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(128))
    param_x: Mapped[str] = mapped_column(
        String(64), nullable=False, default="tp_r", server_default="tp_r"
    )
    param_y: Mapped[str] = mapped_column(
        String(64), nullable=False, default="sl_r", server_default="sl_r"
    )
    metric: Mapped[str] = mapped_column(
        String(64), nullable=False, default="ev", server_default="ev"
    )
    points: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
