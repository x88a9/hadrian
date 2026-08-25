"""OHLC bars: the type the engine consumes, and the contract every source fills.

A backtest is only as trustworthy as the bars it ran on, so the series type is
strict about its invariants and checks them once, at construction, rather than
leaving the engine to discover a duplicated timestamp or an impossible bar in
the middle of a run.

Timestamps are the bar's **open** time, in UTC, always. Every venue and file
format disagrees about this; the disagreement is resolved here at the boundary,
so that nothing downstream has to ask which convention it is holding. A bar
stamped 12:00 on H1 covers [12:00, 13:00) and is not decidable until 13:00 —
that single sentence is what the engine's no-lookahead rule rests on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, Protocol, Sequence, runtime_checkable

__all__ = [
    "TIMEFRAMES",
    "Candle",
    "CandleSeries",
    "CandleSource",
    "CandleDataError",
    "timeframe_delta",
    "normalise_timeframe",
]


class CandleDataError(ValueError):
    """Bars are missing, malformed, or not what was asked for."""


#: Supported bar sizes, mapped to their duration. The keys are the strings used
#: throughout the platform (``systems.timeframe``) and by the Hyperliquid
#: ``/info`` candle endpoint, which is why the spelling is theirs and not a
#: prettier one of ours.
TIMEFRAMES: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
}

#: The workbook and the existing systems table spell timeframes as M15/H1/D1.
#: Both spellings are accepted everywhere; they are folded to the venue's here.
_ALIASES: dict[str, str] = {
    "M1": "1m",
    "M3": "3m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H2": "2h",
    "H4": "4h",
    "H8": "8h",
    "H12": "12h",
    "D1": "1d",
    "D3": "3d",
    "W1": "1w",
}


def normalise_timeframe(timeframe: str) -> str:
    """Fold ``H1`` and ``1h`` onto one spelling.

    Both appear in this codebase — the research workbook writes ``H1``, the
    venue writes ``1h`` — and a mismatch between them is exactly the kind of
    thing that silently backtests a strategy on the wrong bar size.
    """
    raw = (timeframe or "").strip()
    if raw in TIMEFRAMES:
        return raw
    upper = raw.upper()
    if upper in _ALIASES:
        return _ALIASES[upper]
    lower = raw.lower()
    if lower in TIMEFRAMES:
        return lower
    raise CandleDataError(
        f"unknown timeframe {timeframe!r}; known: {', '.join(TIMEFRAMES)} "
        f"(or {', '.join(_ALIASES)})"
    )


def timeframe_delta(timeframe: str) -> timedelta:
    return TIMEFRAMES[normalise_timeframe(timeframe)]


@dataclass(frozen=True, slots=True)
class Candle:
    """One bar. ``ts`` is the open time, UTC, timezone-aware."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise CandleDataError(
                f"candle timestamp {self.ts!r} is naive; bars are UTC-aware so that "
                "no downstream code has to guess the convention"
            )
        body_high = max(self.open, self.close)
        body_low = min(self.open, self.close)
        if self.high < body_high or self.low > body_low:
            raise CandleDataError(
                f"impossible bar at {self.ts.isoformat()}: high={self.high} "
                f"low={self.low} do not contain open={self.open} close={self.close}"
            )
        if self.volume < 0:
            raise CandleDataError(f"negative volume at {self.ts.isoformat()}")

    def as_utc(self) -> "Candle":
        return self if self.ts.tzinfo is timezone.utc else Candle(
            self.ts.astimezone(timezone.utc),
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
        )


class CandleSeries:
    """An ordered, gap-checked run of bars for one asset and timeframe.

    Immutable by construction and cheap to slice. The invariants — strictly
    increasing timestamps, all on the timeframe's grid — are checked once here,
    because a backtest that silently ran over a duplicated or out-of-order bar
    produces a number that looks exactly like a real one.

    Gaps are *allowed* but *recorded*. Venues have outages and thin markets have
    empty periods; refusing the series outright would make whole assets
    unbacktestable. Instead ``gaps`` reports them, so a result can be judged
    against how complete its data was.
    """

    __slots__ = ("asset", "timeframe", "_candles", "_gaps")

    def __init__(self, asset: str, timeframe: str, candles: Sequence[Candle]):
        self.asset = asset
        self.timeframe = normalise_timeframe(timeframe)
        normalised = tuple(c.as_utc() for c in candles)

        step = TIMEFRAMES[self.timeframe]
        gaps: list[tuple[datetime, datetime]] = []
        previous: Candle | None = None
        for candle in normalised:
            if previous is not None:
                if candle.ts == previous.ts:
                    raise CandleDataError(
                        f"duplicate bar at {candle.ts.isoformat()} in {asset} "
                        f"{self.timeframe}"
                    )
                if candle.ts < previous.ts:
                    raise CandleDataError(
                        f"bars are out of order: {candle.ts.isoformat()} follows "
                        f"{previous.ts.isoformat()} in {asset} {self.timeframe}"
                    )
                delta = candle.ts - previous.ts
                if delta % step:
                    raise CandleDataError(
                        f"bar at {candle.ts.isoformat()} is off the {self.timeframe} "
                        f"grid ({delta} since the previous bar is not a multiple of "
                        f"{step})"
                    )
                if delta > step:
                    gaps.append((previous.ts + step, candle.ts))
            previous = candle

        self._candles = normalised
        self._gaps = tuple(gaps)

    # -- sequence behaviour ------------------------------------------------- #

    def __len__(self) -> int:
        return len(self._candles)

    def __iter__(self) -> Iterator[Candle]:
        return iter(self._candles)

    def __getitem__(self, index: int) -> Candle:
        return self._candles[index]

    def __repr__(self) -> str:
        span = f"{self.start.isoformat()}..{self.end.isoformat()}" if self else "empty"
        return f"<CandleSeries {self.asset} {self.timeframe} n={len(self)} {span}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CandleSeries):
            return NotImplemented
        return (
            self.asset == other.asset
            and self.timeframe == other.timeframe
            and self._candles == other._candles
        )

    # -- properties --------------------------------------------------------- #

    @property
    def candles(self) -> tuple[Candle, ...]:
        return self._candles

    @property
    def gaps(self) -> tuple[tuple[datetime, datetime], ...]:
        """Half-open ``[from, to)`` intervals with no bars. Empty when complete."""
        return self._gaps

    @property
    def start(self) -> datetime:
        if not self._candles:
            raise CandleDataError("an empty series has no start")
        return self._candles[0].ts

    @property
    def end(self) -> datetime:
        """Open time of the last bar. Its *close* is ``end + timeframe_delta``."""
        if not self._candles:
            raise CandleDataError("an empty series has no end")
        return self._candles[-1].ts

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self._candles]

    # -- derivation --------------------------------------------------------- #

    def slice(self, start: datetime | None = None, end: datetime | None = None) -> "CandleSeries":
        """Bars in ``[start, end)``. Used for the IS/OOS split, so the boundary
        belongs to exactly one side and no bar is counted twice."""
        selected = [
            c
            for c in self._candles
            if (start is None or c.ts >= start) and (end is None or c.ts < end)
        ]
        return CandleSeries(self.asset, self.timeframe, selected)

    def merge(self, other: "CandleSeries") -> "CandleSeries":
        """Combine two runs of the same series, later bars winning on overlap.

        The cache uses this to extend what it holds without re-fetching. Later
        wins because the newer fetch saw a bar that had since finalised, and a
        venue's last bar is frequently still forming when it is first read.
        """
        if (other.asset, other.timeframe) != (self.asset, self.timeframe):
            raise CandleDataError(
                f"cannot merge {other.asset} {other.timeframe} into "
                f"{self.asset} {self.timeframe}"
            )
        by_ts = {c.ts: c for c in self._candles}
        by_ts.update({c.ts: c for c in other._candles})
        return CandleSeries(
            self.asset, self.timeframe, [by_ts[k] for k in sorted(by_ts)]
        )


@runtime_checkable
class CandleSource(Protocol):
    """Where bars come from.

    Implementations are read-only by construction: a source fetches, it never
    trades. That separation is what lets market data be read from mainnet while
    order execution stays fenced off — see ``app/execution/mode.py``.
    """

    def fetch(
        self,
        asset: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> CandleSeries:
        """Bars for ``[start, end)``, ascending. Raises ``CandleDataError`` when
        the request cannot be served; returns an empty series when it can be
        served but there is nothing there."""
        ...
