from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# Ticket-Lebenszyklus (Phase 7, Teil B). ``cancelled`` ist ein Terminalzustand
# from any active stage; cancelled tickets do NOT count towards the
# Statistik oder in die Kontostand-Fortschreibung.
LIVE_TRADE_STAGES = (
    "setup_sighted",
    "risk_calculated",
    "order_placed",
    "entry_filled",
    "running",
    "closed",
    "cancelled",
)
ENTRY_ORDER_TYPES = ("market", "limit")
LIVE_DIRECTIONS = ("long", "short")
# Break-even statt "draw" (Brief Teil D: |R| < 0.1 -> break-even).
LIVE_WIN_LOSS = ("win", "loss", "break_even")


class LiveTrade(Base):
    """A stateful live trade / ticket (Phase 7).

    Separate from ``trades`` (which are finished backtest rows): a live trade
    carries a lifecycle, fees, slippage and funding that backtests never have.
    The fee / sizing fields are a **snapshot** taken at creation time so a later
    global fee change can never alter a historic trade (hard requirement).
    """

    __tablename__ = "live_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT, not CASCADE as for backtest trades: live fills are real and
    # cannot be reproduced. Deleting a system that still has live trades is
    # rejected with 409 by an API pre-check rather than silently
    # zu kaskadieren (Phase 7).
    # Seit Phase 8 (Migration 0009) NULL-bar: ein „freier" Trade ohne System
    # (a discretionary trade) must still land in the journal cleanly.
    system_id: Mapped[int | None] = mapped_column(
        ForeignKey("systems.id", ondelete="RESTRICT"), nullable=True
    )
    venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("venues.id", ondelete="SET NULL")
    )
    # Version of the asset settings the snapshot came from — informational
    # only; the values used in the calculation are snapshotted below.
    asset_setting_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_settings.id", ondelete="SET NULL")
    )

    asset: Mapped[str | None] = mapped_column(String(32))
    stage: Mapped[str] = mapped_column(
        Enum(*LIVE_TRADE_STAGES, name="live_trade_stage", native_enum=False),
        nullable=False,
        default="setup_sighted",
        server_default="setup_sighted",
    )
    direction: Mapped[str | None] = mapped_column(
        Enum(*LIVE_DIRECTIONS, name="live_trade_direction", native_enum=False)
    )
    entry_order_type: Mapped[str | None] = mapped_column(
        Enum(*ENTRY_ORDER_TYPES, name="entry_order_type", native_enum=False)
    )

    # --- Plan (Stufe 1) --- #
    planned_entry: Mapped[float | None] = mapped_column(Float)
    planned_stop: Mapped[float | None] = mapped_column(Float)

    # --- Execution (stage 4 of 6) --- #
    actual_entry: Mapped[float | None] = mapped_column(Float)
    actual_stop: Mapped[float | None] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float)

    # --- Risk-Rechner-Ergebnis (Stufe 2) --- #
    position_size_coins: Mapped[float | None] = mapped_column(Float)
    position_size_notional: Mapped[float | None] = mapped_column(Float)
    # Leverage required by the calculation, buffer included (e.g. 9.1).
    leverage: Mapped[float | None] = mapped_column(Float)
    # The plain notional/equity ratio (e.g. 8.98) and the integer level
    # actually set on the exchange (e.g. 10). See docs/DECISIONS.md.
    implicit_leverage: Mapped[float | None] = mapped_column(Float)
    exchange_leverage: Mapped[float | None] = mapped_column(Float)
    risk_usd: Mapped[float | None] = mapped_column(Float)
    risk_pct: Mapped[float | None] = mapped_column(Float)
    risk_modifier: Mapped[float | None] = mapped_column(Float)
    # Erwarteter Verlust OHNE Slippage/Fees (= adjusted_exp_loss).
    expected_loss: Mapped[float | None] = mapped_column(Float)

    # --- Result on close (stage 6) --- #
    realized_pnl_usd: Mapped[float | None] = mapped_column(Float)
    r_value: Mapped[float | None] = mapped_column(Float)
    win_loss: Mapped[str | None] = mapped_column(
        Enum(*LIVE_WIN_LOSS, name="live_win_loss", native_enum=False)
    )
    # Execution quality: slippage plus fee deviation.
    deviation_pct: Mapped[float | None] = mapped_column(Float)
    fees_paid: Mapped[float | None] = mapped_column(Float)
    funding_paid: Mapped[float | None] = mapped_column(Float)
    slippage: Mapped[float | None] = mapped_column(Float)
    balance_after: Mapped[float | None] = mapped_column(Float)

    # --- Fee-/Settings-SNAPSHOT (bei Anlage eingefroren, Isolation) --- #
    portfolio_size_at_creation: Mapped[float | None] = mapped_column(Float)
    snap_entry_fee_pct: Mapped[float | None] = mapped_column(Float)
    snap_exit_fee_pct: Mapped[float | None] = mapped_column(Float)
    snap_min_position_size: Mapped[float | None] = mapped_column(Float)
    snap_leverage_buffer: Mapped[float | None] = mapped_column(Float)
    snap_upside_deviation_allowed_pct: Mapped[float | None] = mapped_column(Float)
    snap_downside_deviation_allowed_pct: Mapped[float | None] = mapped_column(Float)
    snap_max_leverage: Mapped[float | None] = mapped_column(Float)
    snap_leverage_step: Mapped[float | None] = mapped_column(Float)
    snap_min_order_value_usd: Mapped[float | None] = mapped_column(Float)

    # --- Zeitstempel pro Stufe --- #
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    setup_sighted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    running_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Holding time in seconds, set on close (the running duration is computed by the
    # UI live aus entry_filled_at/opened_at).
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    rules_followed: Mapped[bool | None] = mapped_column(Boolean)
    chart_url: Mapped[str | None] = mapped_column(String(512))
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

    system: Mapped["System | None"] = relationship()

    __table_args__ = (
        Index("ix_live_trades_system_id", "system_id"),
        Index("ix_live_trades_stage", "stage"),
    )


from app.models.system import System  # noqa: E402
