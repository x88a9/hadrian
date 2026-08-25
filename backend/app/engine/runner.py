"""Running a StrategyDefinition against candles.

The parent half of the engine. It knows about pydantic, the sandbox and the
candle types; everything it delegates to — ``indicators``, ``evaluator``,
``backtest`` — is stdlib-only so that the same code can run inside the sandbox
when the strategy is written in Python.

Which path a definition takes is decided by one field:

* ``rules == "declarative"`` — the rule tree is evaluated in this process.
  There is no untrusted code involved, so there is nothing to sandbox and no
  process to pay for.
* ``rules == "python"`` — the source, the definition and the bars are handed to
  the sandbox, which runs the *same* engine loop around the user's ``on_bar``
  and hands back the trades. The engine is not re-implemented on the other
  side of that boundary; it is the same module, imported there.
"""

from __future__ import annotations

from app.data.candles import CandleSeries, timeframe_delta
from app.engine.backtest import BacktestResult, EngineConfig, EngineTrade, run_backtest
from app.engine.evaluator import build_signal_fn
from app.engine.indicators import compute_specs
from app.strategy.definition import StrategyDefinition
from app.strategy.sandbox import SandboxLimits, run_sandboxed

__all__ = ["bars_from_series", "run_definition"]


def bars_from_series(series: CandleSeries) -> dict[str, list]:
    """The parallel-list form the engine and the indicators both want.

    Built once and shared: an indicator pass and the backtest loop each read
    these lists many times, and rebuilding per-bar objects for either would
    dominate the run.
    """
    return {
        "ts": [c.ts.isoformat() for c in series],
        "open": [c.open for c in series],
        "high": [c.high for c in series],
        "low": [c.low for c in series],
        "close": [c.close for c in series],
        "volume": [c.volume for c in series],
    }


def run_definition(
    definition: StrategyDefinition,
    series: CandleSeries,
    *,
    overrides: dict[str, float] | None = None,
    limits: SandboxLimits | None = None,
) -> BacktestResult:
    """Backtest ``definition`` over ``series`` and return the trades.

    ``overrides`` sets parameter values for this run only, which is what a
    sweep varies. The definition is resolved first either way, so the engine
    never sees a parameter reference and a stored result records the values it
    actually ran with.
    """
    resolved = definition.resolve(overrides)
    payload = resolved.to_json_dict()
    payload["bar_seconds"] = timeframe_delta(resolved.timeframe).total_seconds()

    bars = bars_from_series(series)

    if resolved.rules == "python":
        return _run_in_sandbox(payload, bars, limits)

    indicators = compute_specs(payload["indicators"], bars)
    return run_backtest(
        bars,
        indicators,
        EngineConfig.from_dict(payload),
        build_signal_fn(payload, bars, indicators),
    )


def _run_in_sandbox(
    payload: dict,
    bars: dict[str, list],
    limits: SandboxLimits | None,
) -> BacktestResult:
    """Hand the whole run to the sandbox and reassemble the result.

    One round trip for the entire backtest rather than one per bar. Crossing a
    process boundary tens of thousands of times would cost more than the
    backtest itself, and the user's code has no reason to see the world one
    message at a time — it sees it one *bar* at a time, which the loop on the
    other side provides.
    """
    result = run_sandboxed(
        "backtest",
        {"source": payload["python_source"], "definition": payload, "bars": bars},
        limits=limits or SandboxLimits(timeout_s=60.0, memory_mb=512),
    )
    value = result.value or {}
    return BacktestResult(
        trades=[EngineTrade(**t) for t in value.get("trades", [])],
        bars=value.get("bars", 0),
        warnings=list(value.get("warnings", [])),
        warmup_bars=value.get("warmup_bars", 0),
    )
