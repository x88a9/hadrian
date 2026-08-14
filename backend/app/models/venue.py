from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Venue(Base):
    """A trading venue / exchange (e.g. "CEX", "Hyperliquid"). Asset settings
    hang off a venue (Phase 7)."""

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    asset_settings: Mapped[list["AssetSetting"]] = relationship(
        back_populates="venue",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AssetSetting(Base):
    """Fee / sizing configuration for one asset on one venue, **versioned** by
    ``valid_from`` (Phase 7).

    A fee change never mutates an existing row — it inserts a new version with a
    later ``valid_from``. The setting in force at any instant is the row with the
    greatest ``valid_from`` <= that instant for the (venue, asset) pair. Live
    trades additionally snapshot the concrete values they used, so even deleting
    or superseding a version cannot alter a historic trade.
    """

    __tablename__ = "asset_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    asset: Mapped[str] = mapped_column(String(32), nullable=False)

    entry_fee_pct: Mapped[float] = mapped_column(Float, nullable=False)
    exit_fee_pct: Mapped[float] = mapped_column(Float, nullable=False)
    # Lot-Size des Assets (Hyperliquid: 10^-szDecimals). ASSET-SPEZIFISCH —
    # BTC 0.00001, SOL 0.01, DOT 0.1; many markets trade whole coins.
    min_position_size: Mapped[float] = mapped_column(Float, nullable=False)
    # Exchange limits. Integer-only leverage means a step of 1.0
    # bis max_leverage je Asset; Mindest-Ordervolumen 10 USDC.
    max_leverage: Mapped[float | None] = mapped_column(Float)
    leverage_step: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0"
    )
    min_order_value_usd: Mapped[float | None] = mapped_column(Float)
    leverage_buffer: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.1, server_default="0.1"
    )
    upside_deviation_allowed_pct: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.05, server_default="0.05"
    )
    downside_deviation_allowed_pct: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.05, server_default="0.05"
    )

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    venue: Mapped["Venue"] = relationship(back_populates="asset_settings")

    __table_args__ = (
        UniqueConstraint(
            "venue_id", "asset", "valid_from", name="uq_asset_settings_version"
        ),
    )
