"""The execution journal: every order this system produced, in any mode.

Dry-run orders are recorded exactly like testnet ones, and that is the point.
The journal answers "what would this have done" with the same fidelity as "what
did this do", so a strategy can be watched in dry run for a fortnight and the
record compared against what actually happened on the testnet afterwards.

``mode`` is stored on every row and is never inferred at read time. A row that
did not record which mode produced it would be worse than no row: the one
question this table exists to answer unambiguously is whether something really
went to a venue.
"""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

#: Modes a journal row can carry. Mainnet is absent because no code path in
#: this build can produce such a row, and a vocabulary that admitted one would
#: make the table's own history ambiguous about whether this build ever traded.
EXECUTION_ORDER_MODES = ("dry_run", "testnet")

EXECUTION_ORDER_STATUSES = ("simulated", "filled", "resting", "rejected", "error")


class ExecutionOrder(Base):
    __tablename__ = "execution_orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    #: Generated before the request, so an order can still be recognised when
    #: the response is lost — the case where it matters most.
    client_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(
        Enum(*EXECUTION_ORDER_MODES, name="execution_order_mode", native_enum=False),
        nullable=False,
    )

    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    reference_price: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)

    #: The stage the system was at, and what that scaled its risk to. Kept as
    #: values rather than as a link, because the system's stage moves on and
    #: the order was sized at the stage it had then.
    stage: Mapped[str | None] = mapped_column(String(16))
    stage_scale: Mapped[float | None] = mapped_column(Float)
    requested_risk_usd: Mapped[float | None] = mapped_column(Float)
    realised_risk_usd: Mapped[float | None] = mapped_column(Float)

    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        Enum(
            *EXECUTION_ORDER_STATUSES,
            name="execution_order_status",
            native_enum=False,
        ),
        nullable=False,
    )
    venue_order_id: Mapped[str | None] = mapped_column(String(64))
    filled_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    average_price: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)

    intent: Mapped[dict] = mapped_column(JSONB, nullable=False)
    receipt: Mapped[dict | None] = mapped_column(JSONB)

    system_id: Mapped[int | None] = mapped_column(
        ForeignKey("systems.id", ondelete="SET NULL")
    )
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_execution_orders_mode_created_at", "mode", "created_at"),
    )
