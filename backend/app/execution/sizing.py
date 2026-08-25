"""Position sizing for a live signal, scaled by how proven the system is.

Sizing itself is not reimplemented here. ``services/risk_calc.compute_risk`` is
the verified calculator — it reproduces two hand-checked reference cases to
~1e-8 and this phase does not touch it — and everything below feeds it and
reads its answer. The one thing added is *stage scaling*, and it is added the
way the calculator already supports: through ``risk_modifier``, so the
arithmetic stays inside the module that was verified rather than being applied
afterwards by a second, unverified multiplication.

Why stage scaling exists
------------------------
A system's stage is a claim about how much is known about it.
``backtest`` means it has never traded; ``live_testing`` means it is trading to
find out whether the backtest was real; ``active`` means it earned full size.
Sizing straight off the backtest would put full capital behind an edge that has
only ever existed in a simulation, and every strategy looks good there — see
docs/BENCHMARK_DISCREPANCY.md for what that already cost this project once.

A stage of ``backtest`` or ``retired`` scales to zero. Rather than returning a
zero-size order, which a caller could easily send, that raises: a system that
should not be trading should fail loudly at the sizing step, not produce an
order that happens to be for nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.venue import AssetSetting
from app.services.live_service import inputs_from_setting
from app.services.risk_calc import RiskInputs, RiskResult, compute_risk

__all__ = [
    "STAGE_RISK_SCALE",
    "SizedOrder",
    "StageNotTradeable",
    "size_for_stage",
]

#: How much of the configured risk a system at each stage is allowed to take.
#: Deliberately coarse. A finer schedule would imply a precision about the
#: relationship between stage and confidence that nothing here measures.
STAGE_RISK_SCALE: dict[str, float] = {
    "backtest": 0.0,
    "live_testing": 0.25,
    "active": 1.0,
    "retired": 0.0,
}


class StageNotTradeable(ValueError):
    """The system's stage does not permit live size."""


@dataclass(frozen=True)
class SizedOrder:
    """What the calculator decided, plus the stage context that shaped it."""

    stage: str
    stage_scale: float
    #: The risk that was asked for, before stage scaling.
    requested_risk_usd: float
    #: What was actually put at risk after scaling — ``risk.adjusted_risk``.
    risk: RiskResult

    @property
    def size(self) -> float:
        return self.risk.adjusted_pos_size

    @property
    def tradeable(self) -> bool:
        """Whether this order can actually be placed.

        The calculator can return a valid-looking size that the venue would
        reject — below its minimum order value, or rounded to zero because the
        risk was too small for the asset's lot size. Both are reasons not to
        send, and both are the caller's problem to report rather than discover
        from an exchange error.
        """
        return (
            self.risk.valid_risk
            and not self.risk.rounds_to_zero
            and not self.risk.below_min_order_value
            and not self.risk.leverage_exceeds_max
        )

    def rejection_reason(self) -> str | None:
        if self.risk.rounds_to_zero:
            return (
                f"the position rounds to zero at this venue's lot size "
                f"({self.risk.min_position_size}); the risk is too small to trade "
                "this asset"
            )
        if self.risk.below_min_order_value:
            return (
                f"notional {self.risk.adjusted_notional:.2f} is below the venue's "
                f"minimum order value ({self.risk.min_order_value_usd})"
            )
        if self.risk.leverage_exceeds_max:
            return (
                f"required leverage {self.risk.leverage} exceeds the asset's "
                f"maximum ({self.risk.max_leverage})"
            )
        if not self.risk.valid_risk:
            return (
                f"realised risk {self.risk.adjusted_risk:.4f} falls outside the "
                f"allowed band [{self.risk.risk_lower_bound:.4f}, "
                f"{self.risk.risk_upper_bound:.4f}]"
            )
        return None


def size_for_stage(
    setting: AssetSetting | None,
    *,
    stage: str,
    entry_price: float,
    stop_price: float,
    desired_risk_usd: float,
    portfolio_size: float,
) -> SizedOrder:
    """Size a position for a system at ``stage``.

    Raises :class:`StageNotTradeable` when the stage scales to zero, so a
    system that has not earned live size cannot produce an order at all.
    """
    try:
        scale = STAGE_RISK_SCALE[stage]
    except KeyError:
        raise StageNotTradeable(
            f"unknown system stage {stage!r}; known: "
            f"{', '.join(sorted(STAGE_RISK_SCALE))}"
        ) from None

    if scale <= 0:
        raise StageNotTradeable(
            f"a system at stage {stage!r} does not trade live. Promote it to "
            "'live_testing' first — sizing off a backtest puts capital behind an "
            "edge that has only ever existed in a simulation."
        )

    inputs: RiskInputs = inputs_from_setting(
        setting,
        entry_price=entry_price,
        stop_price=stop_price,
        desired_risk_usd=desired_risk_usd,
        portfolio_size=portfolio_size,
        risk_modifier=scale,
    )
    return SizedOrder(
        stage=stage,
        stage_scale=scale,
        requested_risk_usd=desired_risk_usd,
        risk=compute_risk(inputs),
    )
