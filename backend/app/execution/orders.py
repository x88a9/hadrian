"""What an order is on the way out, and what came back.

One shape for both execution modes. A dry run and a testnet order differ in
what happens to the intent, not in what the intent *is*, and keeping them the
same type is what makes it possible to compare a simulated fill against a real
one without translating between two vocabularies.

Nothing here places an order. :func:`build_executor` is the only way to get
something that can, and it gates on :func:`app.execution.mode.require_permitted`
before it returns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from app.execution.mode import ExecutionMode, require_permitted

__all__ = [
    "Executor",
    "OrderIntent",
    "OrderReceipt",
    "OrderRejected",
    "build_executor",
]


class OrderRejected(RuntimeError):
    """The venue, or the executor, refused the order."""


@dataclass(frozen=True)
class OrderIntent:
    """An order this system wants to place.

    ``client_id`` is generated up front rather than assigned by the venue, so
    an order can be recognised again after a timeout — the case where the
    request succeeded and the response was lost is exactly when you most need
    to know whether it went through.
    """

    asset: str
    direction: str  # "long" | "short"
    size: float
    #: The price the sizing was computed against. Used as a limit with
    #: immediate-or-cancel rather than sending a bare market order, so a thin
    #: book cannot fill this somewhere unrecognisable.
    reference_price: float
    stop_price: float
    reduce_only: bool = False
    #: How far past ``reference_price`` the limit is allowed to sit, as a
    #: fraction. Wide enough to cross the spread, narrow enough that a gap
    #: leaves the order unfilled rather than filled badly.
    slippage_tolerance: float = 0.005
    system_id: int | None = None
    strategy_id: int | None = None
    note: str | None = None
    client_id: str = field(default_factory=lambda: f"hadrian-{uuid.uuid4().hex[:16]}")

    @property
    def is_buy(self) -> bool:
        return self.direction == "long"

    def limit_price(self) -> float:
        """The price to send, with the tolerance applied in the adverse
        direction so the order crosses rather than rests."""
        sign = 1 if self.is_buy else -1
        return self.reference_price * (1 + sign * self.slippage_tolerance)

    def as_dict(self) -> dict:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "size": self.size,
            "reference_price": self.reference_price,
            "stop_price": self.stop_price,
            "reduce_only": self.reduce_only,
            "slippage_tolerance": self.slippage_tolerance,
            "system_id": self.system_id,
            "strategy_id": self.strategy_id,
            "note": self.note,
            "client_id": self.client_id,
        }


@dataclass(frozen=True)
class OrderReceipt:
    """What happened to an intent."""

    client_id: str
    mode: ExecutionMode
    accepted: bool
    #: The venue's identifier, when there is one. Always ``None`` in a dry run —
    #: a fabricated order id would be indistinguishable from a real one in the
    #: journal, which is the one place that must never be ambiguous.
    venue_order_id: str | None = None
    filled_size: float = 0.0
    average_price: float | None = None
    status: str = "simulated"
    message: str | None = None
    raw_response: dict | None = None
    placed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "mode": self.mode.value,
            "accepted": self.accepted,
            "venue_order_id": self.venue_order_id,
            "filled_size": self.filled_size,
            "average_price": self.average_price,
            "status": self.status,
            "message": self.message,
            "placed_at": self.placed_at.isoformat(),
        }


@runtime_checkable
class Executor(Protocol):
    """Something that can turn an intent into a receipt."""

    mode: ExecutionMode

    def place(self, intent: OrderIntent) -> OrderReceipt: ...


def build_executor(mode: ExecutionMode, **kwargs) -> Executor:
    """The only supported way to obtain an executor.

    Gated before anything is constructed, so a refused mode never gets as far
    as having an object that could be called. Importing an executor class
    directly bypasses this, which is why neither of them is exported from the
    package's ``__init__``.
    """
    require_permitted(mode)

    if mode is ExecutionMode.DRY_RUN:
        from app.execution.dry_run import DryRunExecutor

        return DryRunExecutor(**kwargs)

    from app.execution.testnet import TestnetExecutor

    return TestnetExecutor(**kwargs)
