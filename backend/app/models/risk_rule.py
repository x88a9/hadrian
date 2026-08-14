from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RiskRule(Base):
    """A risk limit, global or scoped to a single system (D3).

    ``system_id`` is nullable (global rule when NULL, override otherwise). Only
    the schema + a read-only ``GET /risk-rules`` exist — no breach check or
    alerting in this run.
    """

    __tablename__ = "risk_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    system_id: Mapped[int | None] = mapped_column(
        ForeignKey("systems.id", ondelete="SET NULL")
    )
    max_daily_r: Mapped[float | None] = mapped_column(Float)
    max_weekly_r: Mapped[float | None] = mapped_column(Float)
    max_monthly_r: Mapped[float | None] = mapped_column(Float)
    max_trades_per_day: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
