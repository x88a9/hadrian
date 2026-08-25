"""Turning a signal into a journalled order.

The sequence is deliberately ordered so that the cheapest refusals happen
first and nothing reaches a venue that should not:

1. **Stage.** A system that has not earned live size cannot produce an order at
   all — this raises rather than sizing to zero.
2. **Sizing**, through the verified calculator, with the stage as its risk
   modifier.
3. **Tradeability.** A position that rounds to zero at the venue's lot size, or
   sits below its minimum order value, is journalled as rejected *without the
   executor being called*. Finding that out from an exchange error would mean
   sending an order that was never going to work.
4. **Placement**, through an executor that was gated on the execution mode
   before it was constructed.
5. **Journalling**, always — including for the refusals above, and including
   when the executor raised. An order that failed is exactly the kind that
   needs a record.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.execution.mode import ExecutionMode, require_permitted
from app.execution.orders import Executor, OrderIntent, OrderReceipt, build_executor
from app.execution.sizing import SizedOrder, StageNotTradeable, size_for_stage
from app.models.execution_order import ExecutionOrder
from app.models.system import System
from app.models.venue import AssetSetting

__all__ = ["execute_signal", "journal_order"]


def execute_signal(
    db: Session,
    *,
    system: System,
    setting: AssetSetting | None,
    direction: str,
    entry_price: float,
    stop_price: float,
    desired_risk_usd: float,
    portfolio_size: float,
    mode: ExecutionMode | None = None,
    executor: Executor | None = None,
    strategy_id: int | None = None,
    note: str | None = None,
) -> ExecutionOrder:
    """Size, place and journal one order. Returns the journal row.

    Raises :class:`StageNotTradeable` before anything is written — a system at
    the wrong stage is a caller error, not an order outcome, and journalling it
    as a rejected order would suggest something was attempted.
    """
    resolved_mode = require_permitted(mode or settings.EXECUTION_MODE)

    sized = size_for_stage(
        setting,
        stage=system.status,
        entry_price=entry_price,
        stop_price=stop_price,
        desired_risk_usd=desired_risk_usd,
        portfolio_size=portfolio_size,
    )

    intent = OrderIntent(
        asset=system.asset or "",
        direction=direction,
        size=sized.size,
        reference_price=entry_price,
        stop_price=stop_price,
        system_id=system.id,
        strategy_id=strategy_id,
        note=note,
    )

    reason = sized.rejection_reason()
    if reason is not None:
        return journal_order(
            db,
            intent=intent,
            sized=sized,
            receipt=OrderReceipt(
                client_id=intent.client_id,
                mode=resolved_mode,
                accepted=False,
                status="rejected",
                message=f"not sent: {reason}",
            ),
        )

    active = executor or build_executor(resolved_mode)

    try:
        receipt = active.place(intent)
    except Exception as exc:  # noqa: BLE001 — journalled, then re-raised
        journal_order(
            db,
            intent=intent,
            sized=sized,
            receipt=OrderReceipt(
                client_id=intent.client_id,
                mode=resolved_mode,
                accepted=False,
                status="error",
                message=f"{type(exc).__name__}: {exc}",
            ),
        )
        raise

    return journal_order(db, intent=intent, sized=sized, receipt=receipt)


def journal_order(
    db: Session,
    *,
    intent: OrderIntent,
    sized: SizedOrder | None,
    receipt: OrderReceipt,
) -> ExecutionOrder:
    """Write the row. Called on every outcome, including the failures."""
    row = ExecutionOrder(
        client_id=intent.client_id,
        mode=receipt.mode.value,
        asset=intent.asset,
        direction=intent.direction,
        size=intent.size,
        reference_price=intent.reference_price,
        limit_price=intent.limit_price(),
        stop_price=intent.stop_price,
        stage=sized.stage if sized else None,
        stage_scale=sized.stage_scale if sized else None,
        requested_risk_usd=sized.requested_risk_usd if sized else None,
        realised_risk_usd=sized.risk.adjusted_risk if sized else None,
        accepted=receipt.accepted,
        status=receipt.status,
        venue_order_id=receipt.venue_order_id,
        filled_size=receipt.filled_size,
        average_price=receipt.average_price,
        message=receipt.message,
        intent=intent.as_dict(),
        receipt=receipt.as_dict(),
        system_id=intent.system_id,
        strategy_id=intent.strategy_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
