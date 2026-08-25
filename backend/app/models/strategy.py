"""Strategies, their version history, and the backtests run against them.

A strategy is never edited in place. Every save writes a new
``StrategyVersion``, and ``Strategy.current_version`` points at the newest one.
That costs a row per save and buys the thing this feature would be untrustworthy
without: a result can name the exact definition that produced it, months later,
after the strategy has moved on. Restoring an old version is itself a new
version, so the history stays append-only and nothing is ever rewritten.

``BacktestRun`` keeps its own copy of the trades as JSONB rather than only
writing them to the ``trades`` table. The two serve different readers: the
engine's record carries ``gross_r``, ``cost_r``, ``exit_reason`` and
``bars_held``, which the trades table has no columns for and which are exactly
what you want when asking why a result looks the way it does. When a run is
persisted, the same trades are *also* materialised into a real system so that
every existing metric, walk-forward and Monte-Carlo view applies to an engine
result with no special-casing.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

STRATEGY_RULE_CARRIERS = ("declarative", "python")
BACKTEST_STATUSES = ("ok", "failed")


class Strategy(Base):
    """The mutable head of a strategy: identity, and where its history points."""

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Denormalised from the current version's definition so the list view does
    # not have to parse a JSONB blob per row to render a table.
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    rules: Mapped[str] = mapped_column(
        Enum(*STRATEGY_RULE_CARRIERS, name="strategy_rules", native_enum=False),
        nullable=False,
        default="declarative",
        server_default="declarative",
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StrategyVersion.version",
    )
    runs: Mapped[list["BacktestRun"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class StrategyVersion(Base):
    """One immutable definition. Never updated after it is written."""

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    strategy: Mapped["Strategy"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )


class BacktestRun(Base):
    """One execution of one version against one stretch of candles."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    strategy_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        Enum(*BACKTEST_STATUSES, name="backtest_status", native_enum=False),
        nullable=False,
        default="ok",
    )
    #: Populated only when ``status == "failed"``. A failed run is kept rather
    #: than discarded: "this version does not run, and here is why" is a result.
    error: Mapped[str | None] = mapped_column(Text)

    bars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Caveats the reader needs before trusting the numbers — a position still
    #: open at the end, entries skipped for want of a stop.
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: The same MetricsBlock shape the rest of the platform reports.
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    trades: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: Parameter values this run used, if it overrode the version's defaults.
    overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: The system this run was materialised into, when it was persisted.
    #: SET NULL rather than CASCADE: deleting the system should not erase the
    #: record that the run happened.
    system_id: Mapped[int | None] = mapped_column(
        ForeignKey("systems.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    strategy: Mapped["Strategy"] = relationship(back_populates="runs")

    __table_args__ = (
        Index("ix_backtest_runs_strategy_id_created_at", "strategy_id", "created_at"),
    )
