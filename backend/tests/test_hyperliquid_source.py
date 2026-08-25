"""Tests for ``HyperliquidInfoSource`` against a stubbed transport.

Every test here builds an ``httpx.MockTransport`` — no test in this module
opens a real socket, and none should ever need to: the point of the source
under test is that it can be exercised completely offline.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.data.candles import CandleDataError
from app.data.hyperliquid import HyperliquidInfoSource

UTC = timezone.utc


def _bar(open_ms: int, interval: str = "1h", coin: str = "BTC", *, o=1.0, h=1.0, l=1.0, c=1.0, v=1.0) -> dict:
    close_ms = open_ms + int(timedelta(hours=1).total_seconds() * 1000)
    return {
        "t": open_ms,
        "T": close_ms,
        "s": coin,
        "i": interval,
        "o": str(o),
        "h": str(h),
        "l": str(l),
        "c": str(c),
        "v": str(v),
    }


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _no_sleep(_seconds: float) -> None:
    return None


def _source(handler, **kwargs) -> HyperliquidInfoSource:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HyperliquidInfoSource(
        "https://api.hyperliquid.xyz/info", client=client, sleep=_no_sleep, **kwargs
    )


# --------------------------------------------------------------------------- #
# construction
# --------------------------------------------------------------------------- #


def test_constructor_refuses_a_url_whose_path_is_not_info():
    with pytest.raises(CandleDataError):
        HyperliquidInfoSource("https://api.hyperliquid.xyz/exchange")


def test_constructor_refuses_the_bare_host_with_no_path():
    with pytest.raises(CandleDataError):
        HyperliquidInfoSource("https://api.hyperliquid.xyz")


def test_constructor_accepts_the_info_path():
    HyperliquidInfoSource("https://api.hyperliquid.xyz/info").close()


# --------------------------------------------------------------------------- #
# request shape
# --------------------------------------------------------------------------- #


def test_fetch_posts_the_documented_candle_snapshot_body():
    captured: list[httpx.Request] = []
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 2, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[_bar(_ms(start)), _bar(_ms(start + timedelta(hours=1)))])

    source = _source(handler, now=lambda: end)
    source.fetch("BTC", "1h", start, end)

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/info"
    body = json.loads(request.content)
    assert body["type"] == "candleSnapshot"
    assert body["req"]["coin"] == "BTC"
    assert body["req"]["interval"] == "1h"
    assert body["req"]["startTime"] == _ms(start)
    assert body["req"]["endTime"] == _ms(end)


def test_fetch_converts_open_ms_to_a_utc_aware_datetime():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 1, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_bar(_ms(start))])

    source = _source(handler, now=lambda: end)
    series = source.fetch("BTC", "1h", start, end)
    assert series[0].ts == start
    assert series[0].ts.tzinfo is not None


# --------------------------------------------------------------------------- #
# empty range
# --------------------------------------------------------------------------- #


def test_fetch_returns_an_empty_series_without_a_request_when_end_is_not_after_start():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[])

    source = _source(handler)
    same = datetime(2024, 1, 1, tzinfo=UTC)
    series = source.fetch("BTC", "1h", same, same)
    assert len(series) == 0
    assert calls == []


# --------------------------------------------------------------------------- #
# paging
# --------------------------------------------------------------------------- #


def test_fetch_pages_across_a_response_capped_below_the_full_range():
    """A server that always returns at most 2 bars per call must still be
    fully drained by advancing the cursor to the last bar returned."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=5)
    calls: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        req_start = body["req"]["startTime"]
        req_end = body["req"]["endTime"]
        calls.append((req_start, req_end))
        cursor = datetime.fromtimestamp(req_start / 1000, tz=UTC)
        bars = []
        for _ in range(2):  # server caps each response at 2 bars
            if _ms(cursor) >= req_end:
                break
            bars.append(_bar(_ms(cursor)))
            cursor += timedelta(hours=1)
        return httpx.Response(200, json=bars)

    source = _source(handler, now=lambda: end)
    series = source.fetch("BTC", "1h", start, end)

    assert [c.ts for c in series] == [start + timedelta(hours=i) for i in range(5)]
    assert len(calls) > 1  # genuinely paged, not served in one shot


def test_fetch_advances_past_a_window_with_no_data_instead_of_stopping():
    """A gap in the middle of the range must not truncate everything after it."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=4)
    gap_hour_ts = _ms(start + timedelta(hours=1))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        req_start = body["req"]["startTime"]
        req_end = body["req"]["endTime"]
        bars = []
        cursor_ms = req_start
        while cursor_ms < req_end:
            if cursor_ms != gap_hour_ts:
                bars.append(_bar(cursor_ms))
            cursor_ms += int(timedelta(hours=1).total_seconds() * 1000)
        return httpx.Response(200, json=bars)

    source = _source(handler, now=lambda: end)
    series = source.fetch("BTC", "1h", start, end)

    got = [c.ts for c in series]
    assert start in got
    assert (start + timedelta(hours=1)) not in got  # the gap
    assert (start + timedelta(hours=2)) in got
    assert (start + timedelta(hours=3)) in got


def test_fetch_raises_rather_than_looping_forever_on_a_non_advancing_response():
    """A server that keeps re-serving the same stale bar must not hang."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=10)

    def handler(request: httpx.Request) -> httpx.Response:
        # Always answers with the very first bar, never anything past it.
        return httpx.Response(200, json=[_bar(_ms(start))])

    source = _source(handler, now=lambda: end)
    with pytest.raises(CandleDataError):
        source.fetch("BTC", "1h", start, end)


# --------------------------------------------------------------------------- #
# retries
# --------------------------------------------------------------------------- #


def test_fetch_retries_a_transient_failure_then_succeeds():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, text="server hiccup")
        return httpx.Response(200, json=[_bar(_ms(start))])

    source = _source(handler, now=lambda: end, max_retries=5)
    series = source.fetch("BTC", "1h", start, end)
    assert len(series) == 1
    assert attempts["n"] == 3


def test_fetch_retries_a_connect_error_then_succeeds():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=[_bar(_ms(start))])

    source = _source(handler, now=lambda: end, max_retries=5)
    series = source.fetch("BTC", "1h", start, end)
    assert len(series) == 1
    assert attempts["n"] == 2


def test_fetch_retries_429_then_succeeds():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=[_bar(_ms(start))])

    source = _source(handler, now=lambda: end, max_retries=5)
    series = source.fetch("BTC", "1h", start, end)
    assert len(series) == 1


def test_fetch_gives_up_and_raises_candle_data_error_after_exhausting_retries():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, text="still down")

    source = _source(handler, now=lambda: end, max_retries=2)
    with pytest.raises(CandleDataError):
        source.fetch("BTC", "1h", start, end)
    assert attempts["n"] == 3  # the original try plus 2 retries


def test_fetch_does_not_retry_a_non_429_client_error():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(400, text="bad coin")

    source = _source(handler, now=lambda: end, max_retries=5)
    with pytest.raises(CandleDataError):
        source.fetch("BTC", "1h", start, end)
    assert attempts["n"] == 1  # no retries burned on a request that is just wrong


# --------------------------------------------------------------------------- #
# still-forming last bar
# --------------------------------------------------------------------------- #


def test_fetch_drops_a_bar_still_forming_relative_to_now():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=3)  # requested end is in the future of "now"
    now = start + timedelta(hours=1, minutes=30)  # only the first bar has closed

    all_bars = [_bar(_ms(start)), _bar(_ms(start + timedelta(hours=1)))]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        req_start, req_end = body["req"]["startTime"], body["req"]["endTime"]
        return httpx.Response(
            200, json=[b for b in all_bars if req_start <= b["t"] < req_end]
        )

    source = _source(handler, now=lambda: now)
    series = source.fetch("BTC", "1h", start, end)

    # The bar opening at start+1h closes at start+2h, which is after `now`;
    # it must be dropped as still forming. Only the first bar is closed.
    assert [c.ts for c in series] == [start]


def test_fetch_drops_a_bar_still_forming_relative_to_the_requested_end():
    """Even when `now` is far in the future, a bar whose close is beyond the
    requested `end` must not leak into a series scoped to that end."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)  # bar at `start` closes exactly at `end`
    far_future = end + timedelta(days=365)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_bar(_ms(start))])

    source = _source(handler, now=lambda: far_future)
    series = source.fetch("BTC", "1h", start, end)
    assert [c.ts for c in series] == [start]
