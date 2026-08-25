"""Indicator series, computed in pure Python.

Stdlib only, deliberately. These run inside the sandbox alongside user code,
and everything the sandbox imports is surface untrusted code can reach; a
numpy dependency here would mean allowing numpy in there. The arrays involved
are one-dimensional and a backtest touches each bar once, so the vectorised
version would buy speed the engine does not need and cost isolation it does.

Every function returns a list the same length as its input, with ``None`` for
the warm-up bars where the indicator is not yet defined. ``None`` rather than
zero or the first real value: a strategy must be able to tell "not ready" from
"ready and happens to be zero", and silently substituting a plausible number
during warm-up is a quiet way to invent signals that never existed.

Windows include the current bar. A breakout strategy that wants "the highest
high of the twenty bars *before* this one" asks for ``highest`` with offset 1,
which is explicit and reads correctly; a convention where some indicators
silently excluded the current bar and others did not would not.
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

__all__ = [
    "INDICATORS",
    "INDICATOR_META",
    "IndicatorError",
    "atr",
    "compute",
    "compute_specs",
    "ema",
    "highest",
    "lowest",
    "roc",
    "rsi",
    "sma",
    "stdev",
]


class IndicatorError(ValueError):
    """An indicator was asked for something it cannot compute."""


Series = list[float | None]


def _period(params: Mapping[str, float], default: int | None = None) -> int:
    raw = params.get("period", default)
    if raw is None:
        raise IndicatorError("indicator requires a 'period' parameter")
    period = int(raw)
    if period < 1:
        raise IndicatorError(f"period must be at least 1, got {raw}")
    return period


def sma(values: Sequence[float], period: int) -> Series:
    """Simple moving average.

    Kept as a running sum rather than re-summing each window: over a long
    backtest that is the difference between linear and quadratic, and the two
    agree to floating point here because every term is added and removed
    exactly once.
    """
    out: Series = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    """Exponential moving average, seeded with the SMA of the first window.

    Seeding from the SMA rather than from the first value is the convention
    every charting platform uses; starting from a single bar would leave the
    series visibly wrong for several multiples of the period, which shows up in
    a backtest as trades near the start that no live chart would have taken.
    """
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    multiplier = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = (values[i] - current) * multiplier + current
        out[i] = current
    return out


def rsi(values: Sequence[float], period: int) -> Series:
    """Relative strength index, Wilder's smoothing.

    A period of all-gains gives 100 and all-losses gives 0, which is the
    conventional handling of a zero denominator rather than an error: it is
    what every chart shows, and a strategy comparing against 70 behaves
    correctly at the boundary.
    """
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    if avg_gain == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> Series:
    """Average true range, Wilder's smoothing.

    True range uses the previous close, so the first bar has no true range in
    the strict sense; it is taken as the bar's own range, which is the standard
    treatment and affects only the seed.
    """
    n = len(closes)
    out: Series = [None] * n
    if n < period:
        return out

    true_ranges = [highs[0] - lows[0]]
    for i in range(1, n):
        previous_close = closes[i - 1]
        true_ranges.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - previous_close),
                abs(lows[i] - previous_close),
            )
        )

    current = sum(true_ranges[:period]) / period
    out[period - 1] = current
    for i in range(period, n):
        current = (current * (period - 1) + true_ranges[i]) / period
        out[i] = current
    return out


def stdev(values: Sequence[float], period: int) -> Series:
    """Rolling sample standard deviation, ddof=1.

    Sample rather than population, to match ``metrics.py``: the platform's ECE
    is a sample standard deviation, and two different conventions for the same
    word in one codebase is a bug waiting to be written.
    """
    if period < 2:
        raise IndicatorError(f"stdev needs a period of at least 2, got {period}")
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / (period - 1)
        out[i] = variance**0.5
    return out


def highest(values: Sequence[float], period: int) -> Series:
    """Rolling maximum over the last ``period`` bars, current bar included."""
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = max(values[i - period + 1 : i + 1])
    return out


def lowest(values: Sequence[float], period: int) -> Series:
    """Rolling minimum over the last ``period`` bars, current bar included."""
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = min(values[i - period + 1 : i + 1])
    return out


def roc(values: Sequence[float], period: int) -> Series:
    """Rate of change over ``period`` bars, in percent.

    A zero reference price yields ``None`` rather than an infinity: it cannot
    happen on real price data, and propagating an infinity would poison every
    comparison downstream instead of showing up where it started.
    """
    out: Series = [None] * len(values)
    for i in range(period, len(values)):
        reference = values[i - period]
        out[i] = None if reference == 0 else (values[i] / reference - 1.0) * 100.0
    return out


#: Human-facing description of each indicator: what to call it, whether it
#: reads one price series or the whole bar, and what it can be tuned by.
#:
#: This exists so the block designer can build its own form controls from the
#: engine's actual capabilities rather than from a second list maintained by
#: hand in the frontend. A test asserts every registry entry has one and vice
#: versa, so adding an indicator without describing it fails loudly.
INDICATOR_META: dict[str, dict] = {
    "sma": {
        "label": "Simple moving average",
        "uses_source": True,
        "params": [{"name": "period", "label": "Period", "default": 20, "min": 1}],
    },
    "ema": {
        "label": "Exponential moving average",
        "uses_source": True,
        "params": [{"name": "period", "label": "Period", "default": 20, "min": 1}],
    },
    "rsi": {
        "label": "Relative strength index",
        "uses_source": True,
        "params": [{"name": "period", "label": "Period", "default": 14, "min": 2}],
    },
    "atr": {
        "label": "Average true range",
        # Reads high, low and close together; a source field would be ignored.
        "uses_source": False,
        "params": [{"name": "period", "label": "Period", "default": 14, "min": 1}],
    },
    "stdev": {
        "label": "Rolling standard deviation",
        "uses_source": True,
        "params": [{"name": "period", "label": "Period", "default": 20, "min": 2}],
    },
    "highest": {
        "label": "Highest value in window",
        "uses_source": True,
        "params": [{"name": "period", "label": "Period", "default": 20, "min": 1}],
    },
    "lowest": {
        "label": "Lowest value in window",
        "uses_source": True,
        "params": [{"name": "period", "label": "Period", "default": 20, "min": 1}],
    },
    "roc": {
        "label": "Rate of change (%)",
        "uses_source": True,
        "params": [{"name": "period", "label": "Period", "default": 10, "min": 1}],
    },
}

#: What ``kind`` may be in an ``IndicatorSpec``. Checked against the schema's
#: ``IndicatorKind`` by a test, so the two cannot drift apart.
INDICATORS: dict[str, Callable] = {
    "sma": sma,
    "ema": ema,
    "rsi": rsi,
    "atr": atr,
    "stdev": stdev,
    "highest": highest,
    "lowest": lowest,
    "roc": roc,
}

#: Indicators that need the full bar rather than one price series.
_OHLC_INDICATORS = frozenset({"atr"})


def compute(
    kind: str,
    bars: Mapping[str, Sequence[float]],
    source: str = "close",
    params: Mapping[str, float] | None = None,
) -> Series:
    """Compute one indicator from a mapping of price series.

    ``bars`` holds ``open``/``high``/``low``/``close``/``volume`` as parallel
    lists — the engine builds it once and reuses it for every indicator, which
    is why this takes the mapping rather than a list of bar objects.
    """
    params = params or {}
    if kind not in INDICATORS:
        raise IndicatorError(
            f"unknown indicator {kind!r}; known: {', '.join(sorted(INDICATORS))}"
        )

    if kind in _OHLC_INDICATORS:
        return atr(bars["high"], bars["low"], bars["close"], _period(params))

    try:
        values = bars[source]
    except KeyError:
        raise IndicatorError(
            f"unknown source {source!r}; known: {', '.join(sorted(bars))}"
        ) from None
    return INDICATORS[kind](values, _period(params))


def compute_specs(
    specs: Sequence[Mapping],
    bars: Mapping[str, Sequence[float]],
) -> dict[str, Series]:
    """Compute every indicator a definition declares, keyed by its id.

    Takes the specs as plain dicts — the definition's serialised form — so this
    is usable from inside the sandbox, where the pydantic models are not.
    Parameters must already be resolved; a ``ParamRef`` reaching here is a bug
    upstream and raises rather than being guessed at.
    """
    out: dict[str, Series] = {}
    for spec in specs:
        indicator_id = spec["id"]
        params = spec.get("params") or {}
        for key, value in params.items():
            if isinstance(value, Mapping):
                raise IndicatorError(
                    f"indicator {indicator_id!r} still has an unresolved parameter "
                    f"reference for {key!r}; resolve the definition first"
                )
        out[indicator_id] = compute(
            spec["kind"],
            bars,
            spec.get("source", "close"),
            params,
        )
    return out
