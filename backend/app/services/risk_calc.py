"""Pure, DB-free position-size / risk calculator for live trades.

This is the heart of live trading. The formulas reproduce two hand-checked
reference cases to ~1e-8 (see ``tests/test_risk_calc.py``). Like ``metrics.py`` this module has no ORM or
external dependency beyond the stdlib.

IMPORTANT — position-size adjustment is **ROUND**, not floor.
    The prose in the Phase-7 brief writes ``floor(initial_pos / min_size)`` but
    the brief's own verified numbers contradict that: the SHORT reference case
    (entry 109000 / stop 109900) only reproduces ``adjusted_pos = 0.00312``,
    ``adjusted_notional = 340.08`` and ``adjusted_risk = 3.00388608`` when the
    initial size is **rounded** to the nearest ``min_position_size`` multiple
    (half away from zero, i.e. spreadsheet ``ROUND``). ``floor`` yields 0.00311
    / 338.99 / 2.994… — wrong. The brief is explicit that the verified values
    win over the prose ("wenn deine Implementierung abweicht, ist sie falsch —
    not the code), so ROUND it is. See docs/DECISIONS.md, "Position sizing
    rounds, it does not floor".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class RiskInputs:
    """Everything the calculator needs. Fee/size fields come from the asset
    settings that apply at trade creation time (snapshot — see live_trade).

    ``min_position_size`` is the venue's **lot size for that asset** (on
    Hyperliquid = 10^-szDecimals: BTC 0.00001, SOL 0.01, DOT 0.1, many markets
    trade in whole coins). It is asset-specific — using BTC's step for another
    asset produces sizes that cannot be placed.
    """

    entry_price: float
    stop_price: float
    desired_risk_usd: float
    portfolio_size: float
    entry_fee_pct: float
    exit_fee_pct: float
    min_position_size: float
    leverage_buffer: float = 0.1
    upside_deviation_allowed_pct: float = 0.05
    downside_deviation_allowed_pct: float = 0.05
    risk_modifier: float = 1.0
    # Venue-/Asset-Grenzen (Hyperliquid: ganzzahlige Leverage bis max_leverage,
    # a 10 USDC minimum order size). None disables the check.
    max_leverage: float | None = None
    leverage_step: float = 1.0
    min_order_value_usd: float | None = None


@dataclass(frozen=True)
class RiskResult:
    direction: str  # "long" | "short"
    price_move: float
    effective_desired_risk: float
    initial_pos_size: float
    initial_notional: float
    initial_fees: float
    initial_exp_loss: float
    adjusted_pos_size: float
    adjusted_notional: float
    adjusted_fees: float
    adjusted_exp_loss: float
    adjusted_risk: float
    valid_risk: bool
    risk_lower_bound: float
    risk_upper_bound: float
    # Reference-compatible value: ceil(implied leverage to 1 decimal) + buffer.
    # The leverage *required by the calculation*, safety buffer included.
    leverage: float
    # --- Transparency and exchange limits --- #
    # The step size rounded to — the asset's lot size.
    min_position_size: float
    # Reine Kennzahl: Notional / Kontostand (kann 0.02x sein).
    implicit_leverage: float
    # The level actually settable on the exchange (integer-only on some venues),
    # rounded up from ``leverage``. None when no step grid is known.
    exchange_leverage: float | None
    max_leverage: float | None
    leverage_exceeds_max: bool
    # By how much the rounded risk over- or undershoots the target, in percent.
    risk_overshoot_pct: float
    # The safe alternative one step lower: floored instead of rounded.
    floor_pos_size: float
    floor_risk: float
    floor_valid: bool
    # The position rounds to zero, so it is not tradeable at all.
    rounds_to_zero: bool
    # Notional below the exchange's minimum order size.
    min_order_value_usd: float | None
    below_min_order_value: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _round_to_multiple(value: float, multiple: float) -> float:
    """Round ``value`` to the nearest ``multiple`` (half away from zero).

    Uses ``Decimal`` so e.g. 311.5963.../1 rounds cleanly to 312 and the
    resulting size (0.00312) has no float drift. Generalises to any positive
    ``multiple`` (not just powers of ten).
    """
    if multiple <= 0:
        return value
    v = Decimal(str(value))
    m = Decimal(str(multiple))
    steps = (v / m).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(steps * m)


def _floor_to_multiple(value: float, multiple: float) -> float:
    """Round ``value`` DOWN to the nearest ``multiple`` (safe alternative size)."""
    if multiple <= 0:
        return value
    v = Decimal(str(value))
    m = Decimal(str(multiple))
    steps = (v / m).to_integral_value(rounding=ROUND_FLOOR)
    return float(steps * m)


def _leverage(raw_leverage: float, buffer: float) -> float:
    """Round the raw leverage up to one decimal place, then add the buffer.

    Reproduces the reference ``≈9.1×`` (raw 8.98) and ``≈1.2×`` (raw 1.05):
    ceil(raw, 1 decimal) + buffer. This is the *required* leverage including the
    safety buffer — NOT the number you type into the exchange (see
    ``exchange_leverage``, which snaps this up to an allowed integer step).
    """
    ceil_1dp = (Decimal(str(raw_leverage)) * 10).to_integral_value(
        rounding=ROUND_CEILING
    ) / 10
    return float(ceil_1dp + Decimal(str(buffer)))


def _exchange_leverage(required: float, step: float) -> float | None:
    """Snap the required leverage up to the next selectable exchange step.

    Hyperliquid only accepts **integers** between 1 and the asset's max leverage
    ("Leverage can be set by a user to any integer between 1 and the max
    leverage"), i.e. ``step = 1``. Returns at least one step.
    """
    if step <= 0:
        return None
    r = Decimal(str(required))
    s = Decimal(str(step))
    steps = (r / s).to_integral_value(rounding=ROUND_CEILING)
    if steps < 1:
        steps = Decimal(1)
    return float(steps * s)


def compute_risk(inp: RiskInputs) -> RiskResult:
    entry = inp.entry_price
    stop = inp.stop_price
    fee_sum = inp.entry_fee_pct + inp.exit_fee_pct
    price_move = abs(entry - stop)

    effective_desired = inp.desired_risk_usd * inp.risk_modifier

    denom = price_move + entry * fee_sum
    if denom <= 0:
        raise ValueError("price move + fees must be positive")

    initial_pos = effective_desired / denom
    initial_notional = initial_pos * entry
    initial_fees = initial_pos * entry * fee_sum
    initial_exp_loss = initial_pos * price_move

    adjusted_pos = _round_to_multiple(initial_pos, inp.min_position_size)
    adjusted_notional = adjusted_pos * entry
    adjusted_fees = adjusted_pos * entry * fee_sum
    adjusted_exp_loss = adjusted_pos * price_move
    adjusted_risk = adjusted_exp_loss + adjusted_fees

    lower = effective_desired * (1 - inp.downside_deviation_allowed_pct)
    upper = effective_desired * (1 + inp.upside_deviation_allowed_pct)
    rounds_to_zero = adjusted_pos <= 0
    valid = (not rounds_to_zero) and lower <= adjusted_risk <= upper

    direction = "short" if stop > entry else "long"

    # Implizite Leverage = reine Kennzahl (Notional / Kontostand).
    implicit_leverage = (
        adjusted_notional / inp.portfolio_size if inp.portfolio_size else 0.0
    )
    # Leverage required by the calculation, buffer included.
    leverage = _leverage(implicit_leverage, inp.leverage_buffer)
    # The level actually settable on the exchange (integer-only on some venues).
    exchange_leverage = _exchange_leverage(leverage, inp.leverage_step)
    leverage_exceeds_max = (
        inp.max_leverage is not None
        and exchange_leverage is not None
        and exchange_leverage > inp.max_leverage
    )

    risk_overshoot = (
        (adjusted_risk - effective_desired) / effective_desired * 100.0
        if effective_desired
        else 0.0
    )

    # Sichere Alternative: eine Stufe kleiner (abgerundet).
    floor_pos = _floor_to_multiple(initial_pos, inp.min_position_size)
    floor_risk = floor_pos * price_move + floor_pos * entry * fee_sum
    floor_valid = floor_pos > 0 and lower <= floor_risk <= upper

    below_min_order_value = (
        inp.min_order_value_usd is not None
        and adjusted_pos > 0
        and adjusted_notional < inp.min_order_value_usd
    )

    return RiskResult(
        direction=direction,
        price_move=price_move,
        effective_desired_risk=effective_desired,
        initial_pos_size=initial_pos,
        initial_notional=initial_notional,
        initial_fees=initial_fees,
        initial_exp_loss=initial_exp_loss,
        adjusted_pos_size=adjusted_pos,
        adjusted_notional=adjusted_notional,
        adjusted_fees=adjusted_fees,
        adjusted_exp_loss=adjusted_exp_loss,
        adjusted_risk=adjusted_risk,
        valid_risk=valid,
        risk_lower_bound=lower,
        risk_upper_bound=upper,
        leverage=leverage,
        min_position_size=inp.min_position_size,
        implicit_leverage=implicit_leverage,
        exchange_leverage=exchange_leverage,
        max_leverage=inp.max_leverage,
        leverage_exceeds_max=leverage_exceeds_max,
        risk_overshoot_pct=risk_overshoot,
        floor_pos_size=floor_pos,
        floor_risk=floor_risk,
        floor_valid=floor_valid,
        rounds_to_zero=rounds_to_zero,
        min_order_value_usd=inp.min_order_value_usd,
        below_min_order_value=below_min_order_value,
    )


def deviation_pct(actual: float, expected: float) -> float | None:
    """Execution-quality metric: |actual - expected| / |expected| * 100.

    ``actual``/``expected`` are the realized vs expected loss/gain. Returns None
    when ``expected`` is 0 (undefined).
    """
    if expected == 0:
        return None
    return abs(actual - expected) / abs(expected) * 100.0
