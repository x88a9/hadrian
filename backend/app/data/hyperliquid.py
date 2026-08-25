"""Candles from Hyperliquid's public ``/info`` endpoint.

This is a market-data client, not an exchange client, and the distinction is
enforced in code rather than left to convention: the constructor refuses any
configured URL whose path is not exactly ``/info``, so a misconfigured base
URL cannot quietly turn this into something that posts to an order route. The
module imports nothing that can sign a transaction and holds no key material
— see ``app/execution/mode.py`` for why that split is the whole of the
engine phase's safety boundary. Reading mainnet price history here is fine;
it is not trading.

Paging
------
A single ``candleSnapshot`` call is capped by the venue at roughly 5000 bars,
so a wide request is broken into windows sized to stay under that cap, and
within a window the cursor advances to the *last bar actually returned* (not
to the window's nominal end) so that a response truncated for any reason is
still handled correctly. If a window comes back with nothing new — a real
gap, or a truncated-to-empty response — the cursor is stepped to the next
window rather than the fetch giving up outright, because a thin market's
outage should not cost the rest of the requested range. Progress is checked
explicitly on every step (``next_cursor <= cursor`` raises) so a venue that
repeats the same stale bar forever cannot hang a backtest.

The still-forming last bar
---------------------------
A backtest that let its final bar be one still being built by the venue would
be reading data that has not happened yet by the time the strategy is
supposedly deciding — a lookahead bug with the shape of a normal-looking
bar. Any bar whose close time (``open + timeframe``) is after ``min(end,
now)`` is dropped before the series is returned.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from app.core.config import settings
from app.data.candles import (
    Candle,
    CandleDataError,
    CandleSeries,
    normalise_timeframe,
    timeframe_delta,
)

__all__ = ["HyperliquidInfoSource"]

#: Hyperliquid's approximate per-request cap on candleSnapshot bars. Windows
#: are sized to stay comfortably under it.
_MAX_BARS_PER_WINDOW = 5000

#: Status codes worth retrying: rate limiting and server-side trouble. Any
#: other 4xx means the request itself is wrong and retrying it changes nothing.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}

_DEFAULT_MAX_RETRIES = 4
_BACKOFF_BASE_S = 0.5


class HyperliquidInfoSource:
    """``CandleSource`` backed by ``POST {info_url}`` (``type: candleSnapshot``).

    Read-only by construction: the only network call this class can make is a
    POST to the single URL validated in ``__init__``, and that validation
    requires the URL's path to be ``/info``. There is no method here that
    builds any other URL.
    """

    def __init__(
        self,
        info_url: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 10.0,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        url = info_url if info_url is not None else settings.HL_INFO_URL
        path = httpx.URL(url).path
        if path != "/info":
            raise CandleDataError(
                f"refusing to use {url!r} as the Hyperliquid info endpoint: its "
                f"path is {path!r}, not '/info'. This client is read-only by "
                "construction — it only knows how to POST the public info "
                "route — so any other path (an order route, in particular) is "
                "refused rather than used."
            )
        self._url = url
        self._client = client or httpx.Client(timeout=timeout_s)
        self._owns_client = client is None
        self._max_retries = max_retries
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(timezone.utc))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "HyperliquidInfoSource":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- CandleSource -------------------------------------------------------- #

    def fetch(
        self, asset: str, timeframe: str, start: datetime, end: datetime
    ) -> CandleSeries:
        tf = normalise_timeframe(timeframe)
        if start.tzinfo is None or end.tzinfo is None:
            raise CandleDataError(
                "start/end must be timezone-aware; naive datetimes are exactly "
                "the ambiguity this module exists to remove"
            )
        if end <= start:
            return CandleSeries(asset, tf, [])

        step = timeframe_delta(tf)
        window = step * _MAX_BARS_PER_WINDOW

        bars_by_ts: dict[datetime, Candle] = {}
        cursor = start
        window_end = min(cursor + window, end)
        while cursor < end:
            raw = self._request(asset, tf, cursor, window_end)
            parsed = sorted(
                (self._parse_bar(asset, tf, item) for item in raw),
                key=lambda c: c.ts,
            )
            in_range = [c for c in parsed if start <= c.ts < window_end]

            if in_range:
                for candle in in_range:
                    bars_by_ts[candle.ts] = candle
                next_cursor = in_range[-1].ts + step
                if next_cursor <= cursor:
                    raise CandleDataError(
                        f"Hyperliquid paging for {asset} {tf} made no progress "
                        f"past {cursor.isoformat()}; refusing to loop forever"
                    )
                cursor = next_cursor
            else:
                # Nothing new in this window — a real gap, or a response that
                # truncated to nothing. Either way, move on to the next window
                # instead of abandoning the rest of the requested range.
                cursor = window_end

            if cursor >= window_end:
                window_end = min(cursor + window, end)

        cutoff = min(end, self._now())
        final = [
            candle
            for ts, candle in sorted(bars_by_ts.items())
            if ts + step <= cutoff
        ]
        return CandleSeries(asset, tf, final)

    # -- wire ------------------------------------------------------------- #

    def _request(
        self, asset: str, timeframe: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        body = {
            "type": "candleSnapshot",
            "req": {
                "coin": asset,
                "interval": timeframe,
                "startTime": _to_ms(start),
                "endTime": _to_ms(end),
            },
        }

        attempt = 0
        while True:
            try:
                response = self._client.post(self._url, json=body)
            except httpx.TransportError as exc:
                attempt += 1
                if attempt > self._max_retries:
                    raise CandleDataError(
                        f"Hyperliquid /info request for {asset} {timeframe} "
                        f"failed after {attempt - 1} retries: {exc}"
                    ) from exc
                self._sleep(_BACKOFF_BASE_S * (2 ** (attempt - 1)))
                continue

            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise CandleDataError(
                        f"Hyperliquid /info returned a non-JSON body for "
                        f"{asset} {timeframe}"
                    ) from exc
                if not isinstance(data, list):
                    raise CandleDataError(
                        f"Hyperliquid /info returned {type(data).__name__} for "
                        f"{asset} {timeframe}, expected a list of bars"
                    )
                return data

            if response.status_code in _TRANSIENT_STATUS:
                attempt += 1
                if attempt > self._max_retries:
                    raise CandleDataError(
                        f"Hyperliquid /info gave up on {asset} {timeframe} "
                        f"after {attempt - 1} retries: HTTP "
                        f"{response.status_code}: {response.text[:200]}"
                    )
                self._sleep(_BACKOFF_BASE_S * (2 ** (attempt - 1)))
                continue

            # Any other 4xx means the request is wrong, not unlucky — retrying
            # it would just ask the same broken question again.
            raise CandleDataError(
                f"Hyperliquid /info rejected the request for {asset} "
                f"{timeframe}: HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

    def _parse_bar(
        self, asset: str, timeframe: str, item: dict[str, Any]
    ) -> Candle:
        try:
            ts_ms = item["t"]
            o, h, l, c, v = item["o"], item["h"], item["l"], item["c"], item["v"]
        except KeyError as exc:
            raise CandleDataError(
                f"Hyperliquid bar for {asset} {timeframe} is missing field "
                f"{exc}: {item!r}"
            ) from exc
        ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
        try:
            return Candle(ts, float(o), float(h), float(l), float(c), float(v))
        except (TypeError, ValueError) as exc:
            raise CandleDataError(
                f"Hyperliquid bar for {asset} {timeframe} at {ts.isoformat()} "
                f"is malformed: {item!r}"
            ) from exc


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)
