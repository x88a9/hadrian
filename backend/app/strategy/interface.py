"""The Python authoring interface: what a user's strategy is written against.

Deliberately dependency-free — stdlib only, no pydantic, no numpy. This module
is imported inside the sandbox, and everything the sandbox imports is surface
that untrusted code can reach. Keeping it to the standard library also keeps
the address-space limit meaningful; a sandbox that has to allow numpy needs
half a gigabyte before the user has written a line.

Metadata is declared as plain dicts rather than as the pydantic models from
``definition.py``. The parent process validates those dicts into the real
models, so there is still exactly one place that decides what a valid indicator
or risk block is — it just is not inside the sandbox.

The lookahead guarantee
-----------------------
``Context`` is the only view a strategy has of the market, and it is built
around one index. Every accessor reads backwards from that bar and refuses to
read forward; there is no method that returns a later bar, and asking for one
raises rather than returning something plausible. The strategy cannot cheat by
accident, and a strategy that tries to cheat on purpose gets an exception
instead of a good-looking equity curve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

__all__ = [
    "Bar",
    "Context",
    "LookaheadError",
    "PositionView",
    "Signal",
    "Strategy",
    "StrategyError",
]


class StrategyError(Exception):
    """A user strategy is malformed or misused the interface."""


class LookaheadError(StrategyError):
    """A strategy reached for a bar it is not allowed to see.

    Always a bug in the strategy, and always worth failing the run over: a
    backtest that quietly served the value would produce a number that looks
    like an edge and is not one.
    """


@dataclass(frozen=True, slots=True)
class Bar:
    """One closed bar. ``ts`` is the open time, UTC."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class PositionView:
    """The open position, as the strategy sees it. Read-only: a strategy asks
    for an exit by returning a signal, it does not mutate state."""

    direction: str  # "long" | "short"
    entry_price: float
    stop_price: float
    entry_index: int
    bars_held: int
    unrealised_r: float

    @property
    def is_long(self) -> bool:
        return self.direction == "long"

    @property
    def direction_sign(self) -> int:
        return 1 if self.direction == "long" else -1


@dataclass(frozen=True, slots=True)
class Signal:
    """What a strategy wants to happen at the next bar's open.

    Not *this* bar's close: a decision made on a closed bar can only be acted
    on afterwards, and pretending otherwise is the most common way a backtest
    invents an edge. The engine enforces that; ``Signal`` just names the intent.
    """

    action: str  # "enter_long" | "enter_short" | "exit" | "none"
    #: Override the stop the risk block would have computed. In price terms.
    stop_price: float | None = None
    #: Free-form label carried onto the resulting trade, e.g. which of several
    #: setups fired. Surfaces as the trade's ``zone``.
    tag: str | None = None

    @staticmethod
    def enter_long(stop_price: float | None = None, tag: str | None = None) -> "Signal":
        return Signal("enter_long", stop_price, tag)

    @staticmethod
    def enter_short(stop_price: float | None = None, tag: str | None = None) -> "Signal":
        return Signal("enter_short", stop_price, tag)

    @staticmethod
    def exit(tag: str | None = None) -> "Signal":
        return Signal("exit", None, tag)

    @staticmethod
    def none() -> "Signal":
        return Signal("none")


class Context:
    """Everything a strategy may look at, at one point in time.

    Constructed fresh-looking but cheaply: the underlying series is shared and
    only ``index`` moves, so per-bar cost stays flat over a long backtest.
    """

    __slots__ = ("_bars", "_indicators", "_index", "_params", "_position")

    def __init__(
        self,
        bars: Sequence[Bar],
        indicators: Mapping[str, Sequence[float | None]],
        index: int,
        params: Mapping[str, float],
        position: PositionView | None,
    ):
        self._bars = bars
        self._indicators = indicators
        self._index = index
        self._params = params
        self._position = position

    # -- where we are ------------------------------------------------------- #

    @property
    def index(self) -> int:
        """Index of the bar being decided on."""
        return self._index

    @property
    def bar(self) -> Bar:
        """The current bar. Closed — its high, low and close are final."""
        return self._bars[self._index]

    @property
    def now(self) -> datetime:
        return self._bars[self._index].ts

    @property
    def position(self) -> PositionView | None:
        """The open position, or ``None`` when flat."""
        return self._position

    @property
    def params(self) -> Mapping[str, float]:
        return self._params

    def param(self, name: str, default: float | None = None) -> float:
        try:
            return self._params[name]
        except KeyError:
            if default is not None:
                return default
            raise StrategyError(
                f"undeclared parameter {name!r}; declared: {sorted(self._params)}"
            ) from None

    # -- looking backwards -------------------------------------------------- #

    def _resolve(self, offset: int) -> int:
        if offset < 0:
            raise LookaheadError(
                f"offset {offset} asks for a bar after the one being decided on; "
                "offsets count backwards and start at 0"
            )
        target = self._index - offset
        if target < 0:
            raise IndexError(
                f"offset {offset} reaches before the start of the series "
                f"(only {self._index + 1} bars available)"
            )
        return target

    def bar_at(self, offset: int) -> Bar:
        """The bar ``offset`` bars back. ``bar_at(0)`` is :attr:`bar`."""
        return self._bars[self._resolve(offset)]

    def price(self, field: str = "close", offset: int = 0) -> float:
        bar = self.bar_at(offset)
        try:
            return float(getattr(bar, field))
        except AttributeError:
            raise StrategyError(
                f"unknown price field {field!r}; known: open, high, low, close, volume"
            ) from None

    def history(self, field: str = "close", n: int = 1) -> list[float]:
        """The last ``n`` values of ``field``, oldest first, ending at the
        current bar. Shorter than ``n`` near the start of the series — a
        strategy that needs a minimum warm-up should check ``len``."""
        if n < 1:
            raise StrategyError(f"history length must be at least 1, got {n}")
        start = max(0, self._index - n + 1)
        return [
            float(getattr(bar, field))
            for bar in self._bars[start : self._index + 1]
        ]

    def indicator(self, indicator_id: str, offset: int = 0) -> float | None:
        """A declared indicator's value, ``offset`` bars back.

        ``None`` during the warm-up period, before the indicator has enough
        history. Returning ``None`` rather than raising is deliberate: warm-up
        is normal and a strategy should skip those bars, not crash on them.
        """
        try:
            series = self._indicators[indicator_id]
        except KeyError:
            raise StrategyError(
                f"undeclared indicator {indicator_id!r}; declared: "
                f"{sorted(self._indicators)}"
            ) from None
        return series[self._resolve(offset)]

    def indicator_ready(self, *indicator_ids: str) -> bool:
        """True when every named indicator has a value at this bar. The usual
        first line of an ``on_bar``."""
        return all(self.indicator(i) is not None for i in indicator_ids)


class Strategy:
    """Base class for a strategy written in Python.

    Subclass it, declare the metadata as class attributes, and implement
    ``on_bar``. Everything except ``on_bar`` has a usable default, so the
    smallest working strategy is a handful of lines::

        class Breakout(Strategy):
            name = "20-bar breakout"
            asset = "BTC"
            timeframe = "1h"
            indicators = [
                {"id": "hh", "kind": "highest", "source": "high", "params": {"period": 20}},
                {"id": "atr", "kind": "atr", "params": {"period": 14}},
            ]
            risk = {"stop": {"kind": "atr_multiple", "value": 2.0, "indicator_id": "atr"},
                    "target": {"kind": "r_multiple", "value": 3.0}}

            def on_bar(self, ctx):
                if not ctx.indicator_ready("hh"):
                    return None
                if ctx.position is None and ctx.price("close") > ctx.indicator("hh", 1):
                    return Signal.enter_long()
                return None

    ``on_bar`` may return a :class:`Signal` or ``None``, which means "do
    nothing"; returning ``None`` is the common case and should not require
    ceremony.
    """

    #: Human-readable name. Defaults to the class name.
    name: str = ""
    asset: str = ""
    timeframe: str = ""
    direction: str = "long"
    description: str = ""

    #: ``{"fast": 10}`` or ``{"fast": {"value": 10, "lo": 5, "hi": 20, "step": 5}}``.
    #: The long form declares a sweep range; the short form is shorthand for a
    #: value with no range.
    parameters: dict[str, Any] = {}

    #: Indicator specs as plain dicts — see ``definition.IndicatorSpec``.
    indicators: list[dict[str, Any]] = []

    #: Risk block as a plain dict — see ``definition.RiskSpec``. Required: the
    #: stop defines 1R, and every metric in this platform is denominated in R.
    risk: dict[str, Any] = {}

    #: Cost overrides — see ``definition.CostSpec``. Empty means the verified
    #: venue defaults.
    costs: dict[str, Any] = {}

    def setup(self) -> None:
        """Called once before the first bar. Override to precompute state.

        Anything stored on ``self`` here survives the whole backtest, which is
        the intended place for a strategy's own bookkeeping.
        """

    def on_bar(self, ctx: Context) -> Signal | None:
        """Decide, given everything up to and including ``ctx.bar``.

        Called once per closed bar. A returned entry or exit is filled at the
        *next* bar's open — see :class:`Signal`.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement on_bar(self, ctx)"
        )

    # -- introspection used by the compiler --------------------------------- #

    @classmethod
    def declared_name(cls) -> str:
        return cls.name or cls.__name__
