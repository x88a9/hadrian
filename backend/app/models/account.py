from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Wie ein Kontostand-Historieneintrag zustande kam.
# ``trade_delete``      = compensating entry for a deleted trade,
# ``trade_correction`` = compensating entry after a result was corrected.
ACCOUNT_CHANGE_TYPES = (
    "initial",
    "trade_close",
    "manual",
    "trade_delete",
    "trade_correction",
)


class AccountBalance(Base):
    """Append-only history of the account balance.

    The app carries the balance itself, as a running "balance after trade":
    a seeded ``initial`` row, one ``trade_close`` row appended by each closed
    live trade (never a cancelled one), and user ``manual`` corrections. The
    current balance is the row with the greatest ``as_of`` (id as tiebreak). Built
    so an external reconciliation (Hyperliquid) can later append rows — but no
    Hyperliquid integration in this run.
    """

    __tablename__ = "account_balance"

    id: Mapped[int] = mapped_column(primary_key=True)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    # The PnL that produced this row (None for initial/manual rows).
    delta: Mapped[float | None] = mapped_column(Float)
    # Deliberately a string rather than an enum: the set of change types keeps
    # growing (migration 0009 widened this column to VARCHAR(24)), and strict
    # enum validation would rather drop a ledger row than write it. For an
    # account balance, writing the row always matters more than labelling it.
    change_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="manual",
        server_default="manual",
    )
    live_trade_id: Mapped[int | None] = mapped_column(
        ForeignKey("live_trades.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
