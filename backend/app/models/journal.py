from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

JOURNAL_ENTRY_TYPES = ("note", "daily_review", "trade_review")


class JournalEntry(Base):
    """A live-journal entry (D4 — schema only, no endpoints)."""

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_type: Mapped[str] = mapped_column(
        Enum(*JOURNAL_ENTRY_TYPES, name="journal_entry_type", native_enum=False),
        nullable=False,
        default="note",
        server_default="note",
    )
    system_id: Mapped[int | None] = mapped_column(
        ForeignKey("systems.id", ondelete="SET NULL")
    )
    trade_id: Mapped[int | None] = mapped_column(
        ForeignKey("trades.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(256))
    body: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DailyRiskLog(Base):
    """A per-day realized-risk log (D4 — schema only, no endpoints)."""

    __tablename__ = "daily_risk_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    realized_r: Mapped[float | None] = mapped_column(Float)
    trade_count: Mapped[int | None] = mapped_column(Integer)
    halted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    risk_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_rules.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
