"""Tests for the candle contract (``app/data/candles.py``) and the two
network-free sources that implement it: CSV import and the on-disk cache.

No test in this file opens a socket. Hyperliquid coverage lives in
``test_hyperliquid_source.py`` against a stubbed transport.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.data.cache import CandleCache, CachedCandleSource, _missing_ranges
from app.data.candles import (
    TIMEFRAMES,
    Candle,
    CandleDataError,
    CandleSeries,
    normalise_timeframe,
    timeframe_delta,
)
from app.data.csv_source import CsvCandleSource

UTC = timezone.utc


def _c(hour: int, o: float = 100.0, h: float | None = None, l: float | None = None,
       c: float | None = None, v: float = 1.0, *, day: int = 1) -> Candle:
    """A tidy, always-valid H1 candle at 2024-01-{day} {hour}:00 UTC."""
    close = o if c is None else c
    high = max(o, close) if h is None else h
    low = min(o, close) if l is None else l
    return Candle(datetime(2024, 1, day, hour, tzinfo=UTC), o, high, low, close, v)


# --------------------------------------------------------------------------- #
# candles.py: the contract itself
# --------------------------------------------------------------------------- #


def test_normalise_timeframe_folds_workbook_spelling_onto_venue_spelling():
    assert normalise_timeframe("H1") == "1h"
    assert normalise_timeframe("1h") == "1h"
    assert normalise_timeframe("m15") == "15m"  # tolerate stray lowercase alias too


def test_normalise_timeframe_refuses_unknown_spelling():
    with pytest.raises(CandleDataError):
        normalise_timeframe("7m")


def test_timeframe_delta_matches_the_table():
    assert timeframe_delta("H1") == TIMEFRAMES["1h"]


def test_candle_refuses_a_naive_timestamp():
    with pytest.raises(CandleDataError):
        Candle(datetime(2024, 1, 1, 12), 1, 1, 1, 1)


def test_candle_refuses_a_body_the_high_low_do_not_contain():
    with pytest.raises(CandleDataError):
        Candle(datetime(2024, 1, 1, tzinfo=UTC), open=10, high=9, low=5, close=8)


def test_candle_refuses_negative_volume():
    with pytest.raises(CandleDataError):
        Candle(datetime(2024, 1, 1, tzinfo=UTC), 1, 1, 1, 1, volume=-1)


def test_series_refuses_a_duplicate_timestamp():
    bar = _c(0)
    with pytest.raises(CandleDataError):
        CandleSeries("BTC", "1h", [bar, bar])


def test_series_refuses_out_of_order_bars():
    with pytest.raises(CandleDataError):
        CandleSeries("BTC", "1h", [_c(1), _c(0)])


def test_series_refuses_a_bar_off_the_timeframe_grid():
    off_grid = Candle(datetime(2024, 1, 1, 0, 30, tzinfo=UTC), 1, 1, 1, 1)
    with pytest.raises(CandleDataError):
        CandleSeries("BTC", "1h", [_c(0), off_grid])


def test_series_records_gaps_without_refusing_them():
    series = CandleSeries("BTC", "1h", [_c(0), _c(3)])
    assert series.gaps == ((datetime(2024, 1, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 3, tzinfo=UTC)),)


def test_series_slice_is_half_open():
    series = CandleSeries("BTC", "1h", [_c(0), _c(1), _c(2)])
    sliced = series.slice(datetime(2024, 1, 1, 0, tzinfo=UTC), datetime(2024, 1, 1, 2, tzinfo=UTC))
    assert [c.ts.hour for c in sliced] == [0, 1]


def test_series_merge_prefers_the_later_series_on_overlap():
    original = CandleSeries("BTC", "1h", [_c(0, c=1.0), _c(1)])
    updated = CandleSeries("BTC", "1h", [_c(0, c=2.0)])
    merged = original.merge(updated)
    assert merged[0].close == 2.0
    assert len(merged) == 2


def test_series_merge_refuses_a_different_asset_or_timeframe():
    a = CandleSeries("BTC", "1h", [_c(0)])
    b = CandleSeries("ETH", "1h", [_c(0)])
    with pytest.raises(CandleDataError):
        a.merge(b)


# --------------------------------------------------------------------------- #
# csv_source.py
# --------------------------------------------------------------------------- #


def test_csv_source_reads_a_standard_header():
    text = (
        "time,open,high,low,close,volume\n"
        "2024-01-01T00:00:00+00:00,100,101,99,100.5,10\n"
        "2024-01-01T01:00:00+00:00,100.5,102,100,101,20\n"
    )
    source = CsvCandleSource("BTC", "1h", text=text)
    series = source.fetch("BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC))
    assert len(series) == 2
    assert series[0].open == 100 and series[1].volume == 20


def test_csv_source_accepts_alternate_column_spellings_case_insensitively():
    text = "DATE,O,H,L,C,VOL\n2024-01-01T00:00:00,1,2,0.5,1.5,5\n"
    source = CsvCandleSource("BTC", "1h", text=text)
    series = source.fetch("BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC))
    assert len(series) == 1
    assert series[0].high == 2


def test_csv_source_defaults_volume_to_zero_when_the_column_is_absent():
    text = "time,open,high,low,close\n2024-01-01T00:00:00,1,1,1,1\n"
    series = CsvCandleSource("BTC", "1h", text=text).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert series[0].volume == 0.0


def test_csv_source_refuses_a_missing_required_column():
    text = "time,open,high,close\n2024-01-01T00:00:00,1,1,1\n"  # no low
    with pytest.raises(CandleDataError):
        CsvCandleSource("BTC", "1h", text=text).fetch(
            "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
        )


def test_csv_source_parses_unix_seconds():
    ts = int(datetime(2024, 1, 1, 0, tzinfo=UTC).timestamp())
    text = f"time,open,high,low,close\n{ts},1,1,1,1\n"
    series = CsvCandleSource("BTC", "1h", text=text).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert series[0].ts == datetime(2024, 1, 1, 0, tzinfo=UTC)


def test_csv_source_parses_unix_milliseconds():
    ts_ms = int(datetime(2024, 1, 1, 0, tzinfo=UTC).timestamp() * 1000)
    text = f"time,open,high,low,close\n{ts_ms},1,1,1,1\n"
    series = CsvCandleSource("BTC", "1h", text=text).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert series[0].ts == datetime(2024, 1, 1, 0, tzinfo=UTC)


def test_csv_source_treats_a_naive_iso_timestamp_as_utc():
    text = "time,open,high,low,close\n2024-01-01T00:00:00,1,1,1,1\n"
    series = CsvCandleSource("BTC", "1h", text=text).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert series[0].ts == datetime(2024, 1, 1, 0, tzinfo=UTC)


def test_csv_source_converts_a_non_utc_offset_to_utc():
    text = "time,open,high,low,close\n2024-01-01T02:00:00+02:00,1,1,1,1\n"
    series = CsvCandleSource("BTC", "1h", text=text).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert series[0].ts == datetime(2024, 1, 1, 0, tzinfo=UTC)


def test_csv_source_sorts_out_of_order_rows_ascending():
    text = (
        "time,open,high,low,close\n"
        "2024-01-01T01:00:00,1,1,1,1\n"
        "2024-01-01T00:00:00,1,1,1,1\n"
    )
    series = CsvCandleSource("BTC", "1h", text=text).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert [c.ts.hour for c in series] == [0, 1]


def test_csv_source_refuses_duplicate_timestamps():
    text = (
        "time,open,high,low,close\n"
        "2024-01-01T00:00:00,1,1,1,1\n"
        "2024-01-01T00:00:00,2,2,2,2\n"
    )
    with pytest.raises(CandleDataError):
        CsvCandleSource("BTC", "1h", text=text).fetch(
            "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
        )


def test_csv_source_names_the_offending_line_number_on_a_malformed_row():
    text = (
        "time,open,high,low,close\n"
        "2024-01-01T00:00:00,1,1,1,1\n"
        "2024-01-01T01:00:00,not-a-number,1,1,1\n"
    )
    with pytest.raises(CandleDataError, match=r":3:"):
        CsvCandleSource("BTC", "1h", text=text).fetch(
            "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
        )


def test_csv_source_does_not_silently_drop_a_short_row():
    text = "time,open,high,low,close\n2024-01-01T00:00:00,1,1,1\n"  # missing close value
    with pytest.raises(CandleDataError, match=r":2:"):
        CsvCandleSource("BTC", "1h", text=text).fetch(
            "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
        )


def test_csv_source_skips_blank_lines():
    text = "time,open,high,low,close\n2024-01-01T00:00:00,1,1,1,1\n\n"
    series = CsvCandleSource("BTC", "1h", text=text).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert len(series) == 1


def test_csv_source_refuses_a_request_for_a_different_asset():
    text = "time,open,high,low,close\n2024-01-01T00:00:00,1,1,1,1\n"
    with pytest.raises(CandleDataError):
        CsvCandleSource("BTC", "1h", text=text).fetch(
            "ETH", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
        )


def test_csv_source_refuses_a_request_for_a_different_timeframe():
    text = "time,open,high,low,close\n2024-01-01T00:00:00,1,1,1,1\n"
    with pytest.raises(CandleDataError):
        CsvCandleSource("BTC", "1h", text=text).fetch(
            "BTC", "15m", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
        )


def test_csv_source_reads_from_a_real_file(tmp_path):
    path = tmp_path / "btc_1h.csv"
    path.write_text("time,open,high,low,close\n2024-01-01T00:00:00,1,1,1,1\n")
    series = CsvCandleSource("BTC", "1h", path=path).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)
    )
    assert len(series) == 1


def test_csv_source_requires_exactly_one_of_path_or_text():
    with pytest.raises(CandleDataError):
        CsvCandleSource("BTC", "1h")
    with pytest.raises(CandleDataError):
        CsvCandleSource("BTC", "1h", path="a.csv", text="time,open,high,low,close\n")


# --------------------------------------------------------------------------- #
# cache.py: CandleCache
# --------------------------------------------------------------------------- #


def test_cache_round_trips_a_series(tmp_path):
    cache = CandleCache(tmp_path)
    series = CandleSeries("BTC", "1h", [_c(0), _c(1)])
    cache.save(series)
    loaded = cache.load("BTC", "1h")
    assert loaded == series


def test_cache_load_returns_none_when_nothing_is_stored(tmp_path):
    assert CandleCache(tmp_path).load("BTC", "1h") is None


def test_cache_save_is_keyed_by_asset_and_timeframe(tmp_path):
    cache = CandleCache(tmp_path)
    cache.save(CandleSeries("BTC", "1h", [_c(0)]))
    cache.save(CandleSeries("ETH", "1h", [_c(0)]))
    assert cache.load("BTC", "1h") is not None
    assert cache.load("ETH", "1h") is not None
    assert cache.load("BTC", "15m") is None


def test_cache_save_overwrites_rather_than_appending(tmp_path):
    cache = CandleCache(tmp_path)
    cache.save(CandleSeries("BTC", "1h", [_c(0), _c(1)]))
    cache.save(CandleSeries("BTC", "1h", [_c(0)]))
    assert len(cache.load("BTC", "1h")) == 1


def test_cache_save_writes_no_leftover_temp_file(tmp_path):
    cache = CandleCache(tmp_path)
    cache.save(CandleSeries("BTC", "1h", [_c(0)]))
    names = [p.name for p in tmp_path.iterdir()]
    assert names == ["BTC__1h.jsonl"]


def test_cache_refuses_a_hostile_asset_name_that_tries_to_escape_the_directory(tmp_path):
    cache = CandleCache(tmp_path)
    for hostile in ("../../etc/passwd", "..", "a/b", "a\\b", ""):
        with pytest.raises(CandleDataError):
            cache.path_for(hostile, "1h")


def test_cache_path_for_a_hostile_asset_never_resolves_outside_the_cache_dir(tmp_path):
    cache = CandleCache(tmp_path)
    resolved_dir = tmp_path.resolve()
    for hostile in ("..", "../evil", "a/../../b"):
        try:
            path = cache.path_for(hostile, "1h")
        except CandleDataError:
            continue
        assert resolved_dir in path.parents


def test_cache_corrupt_row_raises_with_the_file_and_line(tmp_path):
    cache = CandleCache(tmp_path)
    path = cache.path_for("BTC", "1h")
    path.write_text('{"ts": 0, "o": 1, "h": 1, "l": 1}\n')  # missing c, v
    with pytest.raises(CandleDataError, match=r":1:"):
        cache.load("BTC", "1h")


# --------------------------------------------------------------------------- #
# cache.py: CachedCandleSource
# --------------------------------------------------------------------------- #


class _CountingSource:
    """An in-memory ``CandleSource`` that records how many times it was hit,
    used to prove the cache actually avoids calling upstream twice."""

    def __init__(self) -> None:
        self.calls: list[tuple[datetime, datetime]] = []

    def fetch(self, asset: str, timeframe: str, start: datetime, end: datetime) -> CandleSeries:
        self.calls.append((start, end))
        step = timeframe_delta(timeframe)
        candles = []
        ts = start
        while ts < end:
            candles.append(Candle(ts, 1.0, 1.0, 1.0, 1.0, 1.0))
            ts += step
        return CandleSeries(asset, timeframe, candles)


def test_cached_source_fetches_upstream_on_a_cold_cache(tmp_path):
    upstream = _CountingSource()
    source = CachedCandleSource(upstream, CandleCache(tmp_path))
    series = source.fetch("BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 3, tzinfo=UTC))
    assert len(series) == 3
    assert len(upstream.calls) == 1


def test_cached_source_second_run_hits_the_cache_and_calls_upstream_zero_times(tmp_path):
    upstream = _CountingSource()
    cache_dir = tmp_path
    start, end = datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 3, tzinfo=UTC)

    CachedCandleSource(upstream, CandleCache(cache_dir)).fetch("BTC", "1h", start, end)
    assert len(upstream.calls) == 1

    # Fresh instances, same cache dir — simulates a second process/run.
    second_upstream = _CountingSource()
    second = CachedCandleSource(second_upstream, CandleCache(cache_dir))
    series = second.fetch("BTC", "1h", start, end)
    assert len(series) == 3
    assert second_upstream.calls == []


def test_cached_source_fetches_only_the_missing_tail(tmp_path):
    upstream = _CountingSource()
    cache = CandleCache(tmp_path)
    source = CachedCandleSource(upstream, cache)

    source.fetch("BTC", "1h", datetime(2024, 1, 1, 0, tzinfo=UTC), datetime(2024, 1, 1, 2, tzinfo=UTC))
    assert upstream.calls == [(datetime(2024, 1, 1, 0, tzinfo=UTC), datetime(2024, 1, 1, 2, tzinfo=UTC))]

    series = source.fetch("BTC", "1h", datetime(2024, 1, 1, 0, tzinfo=UTC), datetime(2024, 1, 1, 4, tzinfo=UTC))
    assert len(series) == 4
    # Second call only asked upstream for the new tail, not the whole range again.
    assert upstream.calls[-1] == (datetime(2024, 1, 1, 2, tzinfo=UTC), datetime(2024, 1, 1, 4, tzinfo=UTC))


def test_cached_source_fetches_only_the_missing_head(tmp_path):
    upstream = _CountingSource()
    cache = CandleCache(tmp_path)
    source = CachedCandleSource(upstream, cache)

    source.fetch("BTC", "1h", datetime(2024, 1, 1, 2, tzinfo=UTC), datetime(2024, 1, 1, 4, tzinfo=UTC))
    source.fetch("BTC", "1h", datetime(2024, 1, 1, 0, tzinfo=UTC), datetime(2024, 1, 1, 4, tzinfo=UTC))
    assert upstream.calls[-1] == (datetime(2024, 1, 1, 0, tzinfo=UTC), datetime(2024, 1, 1, 2, tzinfo=UTC))


def test_cached_source_offline_raises_rather_than_fetching_on_a_miss(tmp_path):
    upstream = _CountingSource()
    source = CachedCandleSource(upstream, CandleCache(tmp_path), offline=True)
    with pytest.raises(CandleDataError):
        source.fetch("BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 2, tzinfo=UTC))
    assert upstream.calls == []


def test_cached_source_offline_still_serves_a_fully_covered_range(tmp_path):
    cache_dir = tmp_path
    warm_upstream = _CountingSource()
    CachedCandleSource(warm_upstream, CandleCache(cache_dir)).fetch(
        "BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 3, tzinfo=UTC)
    )

    offline_source = CachedCandleSource(None, CandleCache(cache_dir), offline=True)
    series = offline_source.fetch("BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 3, tzinfo=UTC))
    assert len(series) == 3


def test_cached_source_without_upstream_raises_on_a_miss(tmp_path):
    source = CachedCandleSource(None, CandleCache(tmp_path))
    with pytest.raises(CandleDataError):
        source.fetch("BTC", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 2, tzinfo=UTC))


def test_missing_ranges_is_empty_for_a_fully_covered_request():
    cached = CandleSeries("BTC", "1h", [_c(0), _c(1), _c(2)])
    assert _missing_ranges(cached, datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 3, tzinfo=UTC), "1h") == []
