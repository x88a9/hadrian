from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

TRADE_DIRECTIONS = ("long", "short")
TRADE_WIN_LOSS = ("win", "loss", "draw")
TRADE_SOURCES = ("manual", "auto", "ui")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[int] = mapped_column(
        ForeignKey("systems.id", ondelete="CASCADE"), nullable=False
    )

    trade_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    zone: Mapped[str | None] = mapped_column(String(64))
    timeframe: Mapped[str | None] = mapped_column(String(16))
    entry: Mapped[float | None] = mapped_column(Float)
    sl: Mapped[float | None] = mapped_column(Float)
    exit: Mapped[float | None] = mapped_column(Float)
    direction: Mapped[str | None] = mapped_column(
        Enum(*TRADE_DIRECTIONS, name="trade_direction", native_enum=False)
    )
    r_value: Mapped[float | None] = mapped_column(Float)
    win_loss: Mapped[str | None] = mapped_column(
        Enum(*TRADE_WIN_LOSS, name="trade_win_loss", native_enum=False)
    )
    source: Mapped[str] = mapped_column(
        Enum(*TRADE_SOURCES, name="trade_source", native_enum=False),
        nullable=False,
        default="manual",
        server_default="manual",
    )

    system: Mapped["System"] = relationship(back_populates="trades")

    __table_args__ = (
        Index("ix_trades_system_id_trade_datetime", "system_id", "trade_datetime"),
    )


from app.models.system import System  # noqa: E402
