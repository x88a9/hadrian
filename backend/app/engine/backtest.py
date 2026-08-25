"""The backtesting engine: bars in, trades out, in R and net of costs.

Stdlib only. The Python authoring path runs this loop *inside the sandbox*
alongside untrusted strategy code, so the engine cannot depend on anything the
sandbox is not willing to import. It also means one engine produces both kinds
of result — a declarative strategy and a hand-written one go through the same
code, and a difference between them can only come from the rules themselves.

How a bar is processed
----------------------
The engine is event-driven over closed bars, and the ordering below is the
whole of its no-lookahead guarantee. For each bar ``i``:

1. If a position is open, resolve it against bar ``i`` — gap at the open first,
   then the stop and target intrabar. The position already existed before this
   bar began, so bar ``i``'s own high and low are fair game.
2. Evaluate the strategy on bar ``i``, which is now closed: its high, low and
   close are final and nothing later exists.
3. A signal produced in step 2 is filled at the **open of bar i+1**, never at
   bar ``i``'s close. A decision made from a closed bar cannot be acted on
   inside that bar, and pretending otherwise is the single most common way a
   backtest invents an edge.
4. Stop adjustments — break-even, trailing — are computed from bar ``i`` and
   take effect from bar ``i+1``, for the same reason.

Two ambiguities, resolved pessimistically
-----------------------------------------
**Stop and target both touched in one bar.** OHLC does not say which came
first, so the engine takes the stop. Choosing the target would make every
result better and some of them fictional; taking the stop understates a
strategy that genuinely got there first, and understating is the error worth
making.

**Gaps.** If a bar opens past the stop, the fill is the open, not the stop —
that is what would have happened, and modelling the stop price would credit
the strategy with liquidity that was not there. A gap through the target is
filled at the open too, which is favourable; the rule is "you get the open",
applied in both directions rather than only the flattering one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

__all__ = [
    "BacktestResult",
    "EngineConfig",
    "EngineError",
    "EngineTrade",
    "Position",
    "run_backtest",
]


class EngineError(ValueError):
    """The engine was asked to run something it cannot."""


@dataclass(frozen=True, slots=True)
class EngineTrade:
    """One completed round trip, in the shape the trades table expects."""

    entry_index: int
    exit_index: int
    entry_ts: str
    exit_ts: str
    direction: str
    entry_price: float
    stop_price: float
    exit_price: float
    r_value: float
    gross_r: float
    cost_r: float
    win_loss: str
    bars_held: int
    exit_reason: str
    tag: str | None = None

    def as_dict(self) -> dict:
        return {
            "entry_index": self.entry_index,
            "exit_index": self.exit_index,
            "entry_ts": self.entry_ts,
            "exit_ts": self.exit_ts,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "exit_price": self.exit_price,
            "r_value": self.r_value,
            "gross_r": self.gross_r,
            "cost_r": self.cost_r,
            "win_loss": self.win_loss,
            "bars_held": self.bars_held,
            "exit_reason": self.exit_reason,
            "tag": self.tag,
        }


@dataclass
class Position:
    """State of the one open position. Mutable, because the stop moves."""

    direction: str
    entry_index: int
    entry_price: float
    stop_price: float
    initial_risk: float
    target_price: float | None
    tag: str | None = None
    moved_to_breakeven: bool = False

    @property
    def sign(self) -> int:
        return 1 if self.direction == "long" else -1

    def unrealised_r(self, price: float) -> float:
        return (price - self.entry_price) * self.sign / self.initial_risk


@dataclass(frozen=True)
class EngineConfig:
    """Everything the loop needs, as plain numbers.

    Deliberately not the pydantic ``StrategyDefinition``: that model lives in
    the parent process and the loop has to run inside the sandbox, where
    pydantic is not importable. The parent flattens the definition into this
    on the way in, which also means the engine cannot accidentally depend on
    some corner of the schema it was never meant to read.
    """

    direction: str = "long"

    stop_kind: str = "percent"
    stop_value: float = 1.0
    stop_indicator: str | None = None
    breakeven_at_r: float | None = None
    trail_atr_multiple: float | None = None

    target_kind: str | None = None
    target_value: float = 2.0
    target_indicator: str | None = None

    max_bars_held: int | None = None

    entry_fee_pct: float = 0.000144
    exit_fee_pct: float = 0.000432
    slippage_pct: float = 0.0
    funding_pct_per_day: float = 0.0

    #: Bar duration in seconds, used only to pro-rate funding.
    bar_seconds: float = 3600.0

    @classmethod
    def from_dict(cls, data: Mapping) -> "EngineConfig":
        """Build from a ``StrategyDefinition``-shaped dict.

        Tolerant of missing blocks so that a definition without a target or
        without cost overrides needs no special-casing at the call site.
        """
        risk = data.get("risk") or {}
        stop = risk.get("stop") or {}
        target = risk.get("target") or None
        costs = data.get("costs") or {}
        return cls(
            direction=data.get("direction", "long"),
            stop_kind=stop.get("kind", "percent"),
            stop_value=float(stop.get("value", 1.0)),
            stop_indicator=stop.get("indicator_id"),
            breakeven_at_r=_optional_float(stop.get("breakeven_at_r")),
            trail_atr_multiple=_optional_float(stop.get("trail_atr_multiple")),
            target_kind=(target or {}).get("kind"),
            target_value=float((target or {}).get("value", 2.0)),
            target_indicator=(target or {}).get("indicator_id"),
            max_bars_held=(
                int(risk["max_bars_held"]) if risk.get("max_bars_held") else None
            ),
            entry_fee_pct=float(costs.get("entry_fee_pct", 0.000144)),
            exit_fee_pct=float(costs.get("exit_fee_pct", 0.000432)),
            slippage_pct=float(costs.get("slippage_pct", 0.0)),
            funding_pct_per_day=float(costs.get("funding_pct_per_day", 0.0)),
            bar_seconds=float(data.get("bar_seconds", 3600.0)),
        )


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


@dataclass
class BacktestResult:
    trades: list[EngineTrade] = field(default_factory=list)
    bars: int = 0
    #: Things a reader should know before trusting the numbers: an open
    #: position at the end, entries skipped for want of a stop, and so on.
    warnings: list[str] = field(default_factory=list)
    #: Bars skipped because an indicator had not warmed up yet.
    warmup_bars: int = 0

    def as_dict(self) -> dict:
        return {
            "trades": [t.as_dict() for t in self.trades],
            "bars": self.bars,
            "warnings": list(self.warnings),
            "warmup_bars": self.warmup_bars,
        }


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #


def run_backtest(
    bars: Mapping[str, Sequence],
    indicators: Mapping[str, Sequence[float | None]],
    config: EngineConfig,
    signal_fn: Callable[[int, Position | None], object],
) -> BacktestResult:
    """Run ``signal_fn`` over ``bars`` and return the trades it produced.

    ``bars`` holds parallel lists keyed ``ts``, ``open``, ``high``, ``low``,
    ``close`` (and optionally ``volume``). ``signal_fn`` is called once per
    closed bar with the bar index and the open position, and returns something
    with an ``action`` attribute or ``None``. The callback is the seam between
    the two authoring paths: the declarative evaluator and a sandboxed user
    strategy both reduce to one.
    """
    opens = bars["open"]
    highs = bars["high"]
    lows = bars["low"]
    closes = bars["close"]
    timestamps = bars["ts"]
    n = len(closes)

    result = BacktestResult(bars=n)
    if n == 0:
        return result

    position: Position | None = None
    pending: tuple[str, float | None, str | None] | None = None

    for i in range(n):
        # -- 1. a fill decided on the previous bar happens at this open ------ #
        if pending is not None:
            action, stop_override, tag = pending
            pending = None
            if action == "exit" and position is not None:
                result.trades.append(
                    _close(position, i, opens[i], "rule", timestamps, config)
                )
                position = None
            elif action in ("enter_long", "enter_short") and position is None:
                position = _open(
                    action, i, opens[i], stop_override, tag, indicators, config, result
                )

        # -- 2. resolve an open position against this bar -------------------- #
        if position is not None:
            closed = _resolve_bar(
                position, i, opens[i], highs[i], lows[i], timestamps, config
            )
            if closed is not None:
                result.trades.append(closed)
                position = None

        if position is not None and config.max_bars_held is not None:
            if i - position.entry_index >= config.max_bars_held:
                result.trades.append(
                    _close(position, i, closes[i], "max_bars", timestamps, config)
                )
                position = None

        # -- 3. ask the strategy, on a bar that is now closed ----------------- #
        if i + 1 < n:
            signal = signal_fn(i, position)
            action = getattr(signal, "action", "none") if signal is not None else "none"
            if action in ("enter_long", "enter_short", "exit"):
                if action == "exit" and position is None:
                    pass  # an exit with nothing open is a no-op, not an error
                elif action != "exit" and position is not None:
                    pass  # one position at a time; the signal is ignored
                elif action == "enter_short" and config.direction == "long":
                    pass
                elif action == "enter_long" and config.direction == "short":
                    pass
                else:
                    pending = (
                        action,
                        getattr(signal, "stop_price", None),
                        getattr(signal, "tag", None),
                    )

        # -- 4. move the stop, effective from the next bar -------------------- #
        if position is not None:
            _adjust_stop(position, i, closes[i], indicators, config)

    if position is not None:
        result.trades.append(
            _close(position, n - 1, closes[n - 1], "end_of_data", timestamps, config)
        )
        result.warnings.append(
            "a position was still open at the end of the data and was closed at the "
            "last bar's close; that trade did not exit on its own terms"
        )

    return result


def _open(
    action: str,
    index: int,
    open_price: float,
    stop_override: float | None,
    tag: str | None,
    indicators: Mapping[str, Sequence[float | None]],
    config: EngineConfig,
    result: BacktestResult,
) -> Position | None:
    """Fill an entry at ``open_price``, or decline it and say why."""
    direction = "long" if action == "enter_long" else "short"
    sign = 1 if direction == "long" else -1

    entry_price = open_price * (1 + sign * config.slippage_pct)

    stop_price = (
        stop_override
        if stop_override is not None
        else _initial_stop(entry_price, sign, index, indicators, config)
    )
    if stop_price is None:
        result.warnings.append(
            f"bar {index}: entry skipped because the stop could not be computed "
            f"(indicator {config.stop_indicator!r} had no value yet)"
        )
        return None

    risk = abs(entry_price - stop_price)
    if risk <= 0:
        # A zero-width stop makes R undefined and would divide by zero two lines
        # later. Skipping the trade is the only honest option.
        result.warnings.append(
            f"bar {index}: entry skipped because the stop ({stop_price}) equals the "
            f"entry ({entry_price}), which leaves R undefined"
        )
        return None
    if (direction == "long" and stop_price >= entry_price) or (
        direction == "short" and stop_price <= entry_price
    ):
        result.warnings.append(
            f"bar {index}: entry skipped because the stop is on the wrong side of "
            f"the entry for a {direction} ({stop_price} vs {entry_price})"
        )
        return None

    return Position(
        direction=direction,
        entry_index=index,
        entry_price=entry_price,
        stop_price=stop_price,
        initial_risk=risk,
        target_price=_target_price(entry_price, stop_price, sign, index, indicators, config),
        tag=tag,
    )


def _initial_stop(
    entry_price: float,
    sign: int,
    index: int,
    indicators: Mapping[str, Sequence[float | None]],
    config: EngineConfig,
) -> float | None:
    kind = config.stop_kind
    if kind == "percent":
        return entry_price * (1 - sign * config.stop_value / 100.0)
    if kind == "fixed_points":
        return entry_price - sign * config.stop_value
    if kind == "atr_multiple":
        atr_value = _indicator_at(indicators, config.stop_indicator, index)
        if atr_value is None:
            return None
        return entry_price - sign * config.stop_value * atr_value
    if kind == "indicator":
        return _indicator_at(indicators, config.stop_indicator, index)
    raise EngineError(f"unknown stop kind {kind!r}")


def _target_price(
    entry_price: float,
    stop_price: float,
    sign: int,
    index: int,
    indicators: Mapping[str, Sequence[float | None]],
    config: EngineConfig,
) -> float | None:
    kind = config.target_kind
    if not kind:
        return None
    if kind == "r_multiple":
        return entry_price + sign * config.target_value * abs(entry_price - stop_price)
    if kind == "percent":
        return entry_price * (1 + sign * config.target_value / 100.0)
    if kind == "indicator":
        return _indicator_at(indicators, config.target_indicator, index)
    raise EngineError(f"unknown target kind {kind!r}")


def _indicator_at(
    indicators: Mapping[str, Sequence[float | None]],
    indicator_id: str | None,
    index: int,
) -> float | None:
    if not indicator_id:
        return None
    try:
        return indicators[indicator_id][index]
    except (KeyError, IndexError):
        return None


def _resolve_bar(
    position: Position,
    index: int,
    open_price: float,
    high: float,
    low: float,
    timestamps: Sequence,
    config: EngineConfig,
) -> EngineTrade | None:
    """Close the position against this bar if the stop or target was reached.

    The order here is the pessimistic reading described in the module
    docstring: a gap decides first, then the stop, then the target.
    """
    long = position.direction == "long"
    stop = position.stop_price
    target = position.target_price

    # A gap through the stop fills at the open, not at the stop: the price was
    # never available in between.
    if (long and open_price <= stop) or (not long and open_price >= stop):
        return _close(position, index, open_price, "stop_gap", timestamps, config)
    if target is not None and ((long and open_price >= target) or (not long and open_price <= target)):
        return _close(position, index, open_price, "target_gap", timestamps, config)

    stop_hit = low <= stop if long else high >= stop
    target_hit = (
        target is not None and (high >= target if long else low <= target)
    )

    if stop_hit:
        # Both touched: OHLC cannot say which came first, so take the stop.
        return _close(position, index, stop, "stop", timestamps, config)
    if target_hit:
        return _close(position, index, target, "target", timestamps, config)
    return None


def _adjust_stop(
    position: Position,
    index: int,
    close: float,
    indicators: Mapping[str, Sequence[float | None]],
    config: EngineConfig,
) -> None:
    """Move the stop, using only bar ``index``. Effective from ``index + 1``."""
    sign = position.sign

    if config.breakeven_at_r is not None and not position.moved_to_breakeven:
        if position.unrealised_r(close) >= config.breakeven_at_r:
            position.stop_price = position.entry_price
            position.moved_to_breakeven = True

    if config.trail_atr_multiple is not None:
        atr_value = _indicator_at(indicators, config.stop_indicator, index)
        if atr_value is not None:
            trailed = close - sign * config.trail_atr_multiple * atr_value
            # Only ever tightens. A stop that could loosen is not a stop.
            if (sign == 1 and trailed > position.stop_price) or (
                sign == -1 and trailed < position.stop_price
            ):
                position.stop_price = trailed


def _close(
    position: Position,
    index: int,
    raw_exit_price: float,
    reason: str,
    timestamps: Sequence,
    config: EngineConfig,
) -> EngineTrade:
    """Book the trade in R, net of costs.

    Costs are expressed per unit of position and then divided by the initial
    risk per unit, which is what makes the result an R figure comparable with
    every other number in this platform: a trade risking 1 % and one risking
    5 % both cost their own R.
    """
    sign = position.sign
    exit_price = raw_exit_price * (1 - sign * config.slippage_pct)

    gross_r = (exit_price - position.entry_price) * sign / position.initial_risk

    bars_held = index - position.entry_index
    fees = (
        position.entry_price * config.entry_fee_pct
        + exit_price * config.exit_fee_pct
    )
    days_held = bars_held * config.bar_seconds / 86400.0
    funding = position.entry_price * config.funding_pct_per_day * days_held
    cost_r = (fees + funding) / position.initial_risk

    net_r = gross_r - cost_r

    return EngineTrade(
        entry_index=position.entry_index,
        exit_index=index,
        entry_ts=str(timestamps[position.entry_index]),
        exit_ts=str(timestamps[index]),
        direction=position.direction,
        entry_price=position.entry_price,
        stop_price=position.stop_price,
        exit_price=exit_price,
        r_value=net_r,
        gross_r=gross_r,
        cost_r=cost_r,
        win_loss=_win_loss(net_r),
        bars_held=bars_held,
        exit_reason=reason,
        tag=position.tag,
    )


def _win_loss(r: float) -> str:
    """Classify a completed trade. Every non-zero R is a win or a loss.

    This deliberately differs from ``metrics.derive_win_loss`` in one band.
    That function reproduces the research workbook's fallback rule, under which
    ``-0.1 <= R < 0`` classifies as *nothing at all* — the cell was left blank
    in the spreadsheet, and the importer has to reproduce that faithfully to
    reconcile against the workbook's own figures.

    The engine is not reproducing a spreadsheet. It watched the trade happen
    and knows that a trade closing at -0.05R is a loss, so it says so. Carrying
    the blank-cell quirk into generated results would leave small losses
    unclassified and quietly undercount ``losses`` for every engine system.

    Outside that band the two agree exactly, which is what the test asserts;
    inside it the divergence is intentional and checked, so it cannot drift
    into being accidental. See docs/DECISIONS.md, "Engine trades classify their
    own outcome".
    """
    if r > 0:
        return "win"
    if r < 0:
        return "loss"
    return "draw"
