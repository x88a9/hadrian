from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

SYSTEM_STATUSES = ("backtest", "live_testing", "active", "retired")
IMPORT_STATUSES = ("complete", "incomplete", "skipped")
SYSTEM_PROVENANCES = ("manual", "programmatic")
SYSTEM_ORIGINS = ("import", "ui")


class System(Base):
    __tablename__ = "systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    prefix: Mapped[str | None] = mapped_column(String(16))
    timeframe: Mapped[str | None] = mapped_column(String(16))
    # The asset the system was backtested on. Systems are almost always tested
    # against exactly one asset (BTC, DOT, XMR ...); live trades inherit it and
    # therefore resolve the correct lot size.
    asset: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        Enum(*SYSTEM_STATUSES, name="system_status", native_enum=False),
        nullable=False,
        default="backtest",
        server_default="backtest",
    )
    entry_rule: Mapped[str | None] = mapped_column(Text)
    sl_rule: Mapped[str | None] = mapped_column(Text)
    tp_rule: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    import_status: Mapped[str] = mapped_column(
        Enum(*IMPORT_STATUSES, name="import_status", native_enum=False),
        nullable=False,
        default="incomplete",
        server_default="incomplete",
    )
    reported_metrics: Mapped[dict | None] = mapped_column(JSONB)
    provenance: Mapped[str] = mapped_column(
        Enum(*SYSTEM_PROVENANCES, name="system_provenance", native_enum=False),
        nullable=False,
        default="manual",
        server_default="manual",
    )
    source_engine: Mapped[str | None] = mapped_column(String(32))
    # Anlage-Kanal (Phase 6, D1): 'import' = via Importer, 'ui' = via POST /systems.
    # Streng getrennt von ``provenance`` (Datenherkunft manual/programmatic).
    origin: Mapped[str] = mapped_column(
        Enum(*SYSTEM_ORIGINS, name="system_origin", native_enum=False),
        nullable=False,
        default="import",
        server_default="import",
    )
    # Field names that were overridden in the UI and are therefore left alone
    # by a re-import (see docs/DECISIONS.md, "Re-import protection"). Always
    # assign a NEW list on update — an in-place append is invisible to
    # SQLAlchemy's change detection.
    user_overrides: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    trades: Mapped[list["Trade"]] = relationship(
        back_populates="system",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


from app.models.trade import Trade  # noqa: E402
