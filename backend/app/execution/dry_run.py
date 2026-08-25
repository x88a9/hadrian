"""The default executor: computes the order, journals it, opens no socket.

A dry run is not a stub. It is the mode this system runs in unless someone
deliberately says otherwise, and it is where the sizing, the stage gate and the
order construction are exercised every time — so it has to produce a receipt
that is honest about being simulated rather than one that merely looks real.

Two things it deliberately does not do. It does not invent a venue order id: a
fabricated identifier in the journal would be indistinguishable from one the
exchange actually issued, and the journal is the one place that must never be
ambiguous about whether something really happened. And it does not model a
partial fill or a rejection — the fill is the limit price, in full. Guessing at
how the book would have behaved would produce a number with the shape of
evidence and none of the substance; what a dry run can honestly report is what
was *asked for*, and that is what it reports.
"""

from __future__ import annotations

from app.execution.mode import ExecutionMode
from app.execution.orders import OrderIntent, OrderReceipt

__all__ = ["DryRunExecutor"]


class DryRunExecutor:
    """Simulated execution. No network, ever."""

    mode = ExecutionMode.DRY_RUN

    def __init__(self, **_ignored) -> None:
        # Accepts and discards the keyword arguments the testnet executor needs
        # (credentials, a client), so ``build_executor`` can pass the same
        # kwargs regardless of mode and a caller does not have to branch.
        pass

    def place(self, intent: OrderIntent) -> OrderReceipt:
        return OrderReceipt(
            client_id=intent.client_id,
            mode=self.mode,
            accepted=True,
            venue_order_id=None,
            filled_size=intent.size,
            average_price=intent.limit_price(),
            status="simulated",
            message=(
                f"dry run: would {'buy' if intent.is_buy else 'sell'} "
                f"{intent.size} {intent.asset} at "
                f"{intent.limit_price():.8f} (stop {intent.stop_price})"
            ),
        )
