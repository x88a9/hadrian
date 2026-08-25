"""OHLC bars from a CSV file or an already-in-memory blob of CSV text.

Research CSVs come from wherever the operator's data vendor happens to export
them, so this reader tolerates the handful of column spellings that actually
show up in practice (``time``/``timestamp``/``date``/``open_time``/``t``, and
the usual one-letter forms for OHLCV) rather than requiring one canonical
header. What it does not tolerate is a bad row: a malformed value is a
``CandleDataError`` naming the offending line, never a silently dropped bar —
a backtest that ran on fewer bars than its source file contains, without
being told so, is worse than one that refused to start.

Timestamp convention
---------------------
Three encodings are accepted: ISO-8601 (with or without a timezone offset),
unix seconds, and unix milliseconds — distinguished by magnitude, since a
millisecond value for any date in this millennium is at least 10**12 and a
seconds value never is. A **naive** timestamp (no offset, no ``Z``) is
interpreted as UTC. That is a choice, not a detection: CSV exports routinely
drop the timezone entirely, and guessing a different zone per file (or per
row) would silently shift every bar in a way nothing downstream could catch.
Operators exporting local time must convert before import.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from app.data.candles import Candle, CandleDataError, CandleSeries, normalise_timeframe

__all__ = ["CsvCandleSource"]

#: Accepted header spellings per canonical field, matched case-insensitively.
#: Volume is the only optional one — its absence defaults each bar to 0.0.
_COLUMN_ALIASES: dict[str, set[str]] = {
    "time": {"time", "timestamp", "date", "open_time", "t"},
    "open": {"open", "o"},
    "high": {"high", "h"},
    "low": {"low", "l"},
    "close": {"close", "c"},
    "volume": {"volume", "vol", "v"},
}

_REQUIRED_COLUMNS = ("time", "open", "high", "low", "close")

#: A millisecond timestamp for any date since 2001-09-09 is >= this; a
#: seconds timestamp for any realistic date never is.
_MS_THRESHOLD = 10**12

_INT_RE = re.compile(r"[+-]?\d+")
_FLOAT_RE = re.compile(r"[+-]?\d+\.\d+")


class CsvCandleSource:
    """``CandleSource`` reading one asset/timeframe from a CSV file or blob.

    Each instance is scoped to a single ``(asset, timeframe)`` — a CSV file
    holds one series, not a market's worth of them — so ``fetch`` refuses a
    request for anything else rather than silently returning the wrong bars.
    """

    def __init__(
        self,
        asset: str,
        timeframe: str,
        *,
        path: str | Path | None = None,
        text: str | None = None,
    ) -> None:
        if (path is None) == (text is None):
            raise CandleDataError(
                "CsvCandleSource needs exactly one of path= or text= "
                f"(got path={path!r}, text={'<set>' if text is not None else None})"
            )
        self._asset = asset
        self._timeframe = normalise_timeframe(timeframe)
        self._path = Path(path) if path is not None else None
        self._text = text

    def fetch(
        self, asset: str, timeframe: str, start: datetime, end: datetime
    ) -> CandleSeries:
        if asset != self._asset:
            raise CandleDataError(
                f"this source only serves {self._asset!r}, not {asset!r}"
            )
        tf = normalise_timeframe(timeframe)
        if tf != self._timeframe:
            raise CandleDataError(
                f"this source only serves {self._timeframe!r} bars, not {tf!r}"
            )
        return self._load().slice(start, end)

    def _load(self) -> CandleSeries:
        source_name = str(self._path) if self._path is not None else "<text>"
        raw_text = self._text if self._text is not None else self._path.read_text()
        return _parse_csv(self._asset, self._timeframe, raw_text, source=source_name)


def _parse_csv(asset: str, timeframe: str, text: str, *, source: str) -> CandleSeries:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return CandleSeries(asset, timeframe, [])

    columns = _resolve_columns(header, source=source)

    candles: list[Candle] = []
    for line_no, row in enumerate(reader, start=2):  # header occupies line 1
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < len(header):
            raise CandleDataError(
                f"{source}:{line_no}: row has {len(row)} fields, expected "
                f"{len(header)}: {row!r}"
            )
        try:
            ts = _parse_timestamp(row[columns["time"]])
            open_ = float(row[columns["open"]])
            high = float(row[columns["high"]])
            low = float(row[columns["low"]])
            close = float(row[columns["close"]])
            volume = (
                float(row[columns["volume"]]) if "volume" in columns else 0.0
            )
        except ValueError as exc:
            raise CandleDataError(
                f"{source}:{line_no}: malformed row {row!r}: {exc}"
            ) from exc
        try:
            candles.append(Candle(ts, open_, high, low, close, volume))
        except CandleDataError as exc:
            raise CandleDataError(f"{source}:{line_no}: {exc}") from exc

    candles.sort(key=lambda c: c.ts)
    # Duplicate timestamps, out-of-order grid alignment, etc. are refused by
    # CandleSeries itself — the invariants only need checking in one place.
    return CandleSeries(asset, timeframe, candles)


def _resolve_columns(header: Sequence[str], *, source: str) -> dict[str, int]:
    normalised = [cell.strip().lower() for cell in header]
    columns: dict[str, int] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        idx = next((i for i, cell in enumerate(normalised) if cell in aliases), None)
        if idx is None:
            if canonical not in _REQUIRED_COLUMNS:
                continue
            raise CandleDataError(
                f"{source}: header {header!r} has no column for {canonical!r} "
                f"(accepted spellings: {sorted(_COLUMN_ALIASES[canonical])})"
            )
        columns[canonical] = idx
    return columns


def _parse_timestamp(raw: str) -> datetime:
    text = raw.strip()
    if not text:
        raise ValueError("empty timestamp")

    if _INT_RE.fullmatch(text):
        value = int(text)
        seconds = value / 1000 if abs(value) >= _MS_THRESHOLD else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    if _FLOAT_RE.fullmatch(text):
        value = float(text)
        seconds = value / 1000 if abs(value) >= _MS_THRESHOLD else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError as exc:
        raise ValueError(f"unrecognised timestamp {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
