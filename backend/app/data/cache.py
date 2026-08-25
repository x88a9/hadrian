"""A local, on-disk cache of candles, and a ``CandleSource`` that uses it.

Reproducibility is the point: the second run of the same backtest must read
the same bars as the first without opening a socket, so that a result can be
re-derived offline, in CI, or a year later against a venue that has since
changed its history. ``CandleCache`` stores one file per ``(asset,
timeframe)``; ``CachedCandleSource`` wraps an upstream ``CandleSource`` and
serves from disk whenever the disk already has what was asked for, fetching
(and persisting) only the part that is missing.

File format
-----------
JSON Lines, one bar per line. Chosen over a binary format (e.g. ``npz``)
because the cache directory is meant to be inspectable during development —
``cat``, ``wc -l``, a `git diff` on a small fixture — without pulling in
numpy as a dependency of the cache path itself, and because a backtest's
candle volumes (thousands to low millions of rows) are nowhere near where a
JSON line's per-row overhead would matter.

Atomicity
---------
A write goes to a temp file in the same directory and is moved into place
with ``os.replace``, which is atomic on the platforms this runs on. A process
killed mid-write leaves the temp file orphaned and the real cache file
exactly as it was before — never a truncated one that a later read would
silently misparse as "fewer bars than we actually have".

Path safety
-----------
The cache file name is built from the asset and timeframe strings, which may
originate from user input (an uploaded workbook, a request body). Both are
passed through a whitelist-character check that refuses path separators,
``.``/``..``, and anything outside a conservative safe set, so a hostile
asset name cannot be used to write outside ``CANDLE_CACHE_DIR``.

Known limitation
-----------------
Coverage is inferred from the min/max timestamp of the bars actually held,
not tracked as separate fetch-range metadata. That means a range that was
queried and legitimately came back *empty* (an asset that did not exist yet,
a venue outage the whole window) cannot be distinguished from a range never
queried at all, and will be re-fetched on every run. Getting that right needs
a coverage record independent of the bars, which is more machinery than this
phase needs; noted here so it is a deliberate gap rather than a surprise.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.data.candles import (
    Candle,
    CandleDataError,
    CandleSeries,
    CandleSource,
    normalise_timeframe,
    timeframe_delta,
)

__all__ = ["CandleCache", "CachedCandleSource"]

#: Conservative filename-safe character set. No path separators, no leading
#: '.', nothing that could be mistaken for a shell or filesystem special.
_SAFE_COMPONENT_RE = re.compile(r"[A-Za-z0-9_.:-]+")


def _sanitise_component(value: str, *, what: str) -> str:
    if not value or value != value.strip():
        raise CandleDataError(f"{what} {value!r} is not a safe cache key")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise CandleDataError(
            f"{what} {value!r} is not a safe cache key: path separators and "
            "'.'/'..' are refused"
        )
    if not _SAFE_COMPONENT_RE.fullmatch(value):
        raise CandleDataError(
            f"{what} {value!r} contains characters outside the safe cache-key "
            f"set {_SAFE_COMPONENT_RE.pattern!r}"
        )
    return value


class CandleCache:
    """One JSON-lines file per ``(asset, timeframe)`` under ``cache_dir``."""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._dir = Path(cache_dir if cache_dir is not None else settings.CANDLE_CACHE_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, asset: str, timeframe: str) -> Path:
        tf = normalise_timeframe(timeframe)
        safe_asset = _sanitise_component(asset, what="asset")
        safe_tf = _sanitise_component(tf, what="timeframe")
        resolved_dir = self._dir.resolve()
        path = (resolved_dir / f"{safe_asset}__{safe_tf}.jsonl").resolve()
        if path.parent != resolved_dir:
            raise CandleDataError(
                f"refusing to write a cache file outside {resolved_dir}: {path}"
            )
        return path

    def load(self, asset: str, timeframe: str) -> CandleSeries | None:
        """``None`` when nothing is cached yet; an empty series is different
        from "not cached" and is returned as such if it was ever stored."""
        path = self.path_for(asset, timeframe)
        if not path.exists():
            return None
        tf = normalise_timeframe(timeframe)
        candles: list[Candle] = []
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    ts = datetime.fromtimestamp(row["ts"] / 1000, tz=timezone.utc)
                    candles.append(
                        Candle(ts, row["o"], row["h"], row["l"], row["c"], row["v"])
                    )
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise CandleDataError(
                        f"{path}:{line_no}: corrupt cache row: {exc}"
                    ) from exc
        return CandleSeries(asset, tf, candles)

    def save(self, series: CandleSeries) -> None:
        """Overwrite the cache file for ``series``'s (asset, timeframe) with
        exactly the bars in ``series``. Callers that want to extend rather
        than replace what is on disk should ``load`` then ``.merge()`` first —
        this method does not merge on its own, so it stays trivially atomic."""
        path = self.path_for(series.asset, series.timeframe)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for candle in series:
                    fh.write(
                        json.dumps(
                            {
                                "ts": int(candle.ts.timestamp() * 1000),
                                "o": candle.open,
                                "h": candle.high,
                                "l": candle.low,
                                "c": candle.close,
                                "v": candle.volume,
                            }
                        )
                    )
                    fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
            raise


def _missing_ranges(
    cached: CandleSeries | None, start: datetime, end: datetime, timeframe: str
) -> list[tuple[datetime, datetime]]:
    """The sub-range(s) of ``[start, end)`` not already spanned by ``cached``.

    Coverage is judged by the cached series' own start/end, extended by one
    step past its last bar (a bar's own span reaches to ``ts + timeframe``).
    An empty or absent cache counts as fully missing — see the module
    docstring's "known limitation".
    """
    if cached is None or len(cached) == 0:
        return [(start, end)]
    step = timeframe_delta(timeframe)
    ranges: list[tuple[datetime, datetime]] = []
    if start < cached.start:
        ranges.append((start, min(cached.start, end)))
    if end > cached.end + step:
        ranges.append((max(cached.end + step, start), end))
    return ranges


class CachedCandleSource:
    """``CandleSource`` that serves from a ``CandleCache``, filling gaps from
    an upstream source and persisting what it fetches.

    ``offline=True`` turns a cache miss into a ``CandleDataError`` instead of
    a network call — the mode a re-run of a stored backtest should use, so
    that "no cache" fails loudly rather than silently re-fetching (and
    possibly getting different bars than the run being reproduced saw).
    """

    def __init__(
        self,
        upstream: CandleSource | None,
        cache: CandleCache,
        *,
        offline: bool = False,
    ) -> None:
        self._upstream = upstream
        self._cache = cache
        self._offline = offline

    def fetch(
        self, asset: str, timeframe: str, start: datetime, end: datetime
    ) -> CandleSeries:
        tf = normalise_timeframe(timeframe)
        if end <= start:
            return CandleSeries(asset, tf, [])

        cached = self._cache.load(asset, tf)
        missing = _missing_ranges(cached, start, end, tf)
        if not missing:
            assert cached is not None  # nothing is "missing" from an absent cache
            return cached.slice(start, end)

        if self._offline:
            raise CandleDataError(
                f"{asset} {tf} is missing {missing!r} from the cache and "
                "offline=True refuses to fetch it"
            )
        if self._upstream is None:
            raise CandleDataError(
                f"{asset} {tf} is not fully cached and no upstream source is "
                "configured to fill the gap"
            )

        merged = cached
        for range_start, range_end in missing:
            if range_end <= range_start:
                continue
            fetched = self._upstream.fetch(asset, tf, range_start, range_end)
            merged = fetched if merged is None else merged.merge(fetched)

        if merged is None:
            merged = CandleSeries(asset, tf, [])
        if len(merged):
            self._cache.save(merged)
        return merged.slice(start, end)
