"""Parser for Hadrian²-style CSV trade exports (Phase 2, D5).

Pure and DB-free: turns raw CSV bytes into a list of :class:`ParsedTrade`
rows (reused from the xlsx importer) plus a count of skipped rows. Uses only
the stdlib ``csv`` module -- pandas is deliberately not a backend dependency.

Column mapping (D5, from the Hadrian² column list in the master prompt, since
``hadrian2_spec.md`` is not shipped):

    entry_time   -> trade_datetime
    direction    -> direction        (long/short, buy/sell normalized)
    entry_price  -> entry
    sl_price     -> sl
    exit_price   -> exit
    net_r        -> r_value          (NET R!)
    timeframe    -> timeframe        (if present)

``win_loss`` is derived from ``net_r`` (derive_win_loss). The columns
``exit_time``, ``tp_price``, ``exit_reason``, ``gross_r`` and any other extras
are discarded (no Trade-model migration in Phase 2).

Robustness rules:
- Numbers: ``float()`` in a ``try``; ``NaN`` / empty / error strings -> None.
- Datetimes: ``datetime.fromisoformat`` plus a few common formats -> None if
  unparseable.
- A row with not a single parseable target field is skipped and counted.
- A header carrying none of the known columns raises ``ValueError`` (the API
  layer turns that into a 400).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from app.importers.xlsx import ParsedTrade
from app.services.metrics import derive_win_loss

# At least one of these must appear in the header, else the file is rejected.
_KNOWN_COLUMNS = {
    "entry_time",
    "direction",
    "entry_price",
    "exit_price",
    "sl_price",
    "net_r",
}

# Additional datetime formats tried after ``fromisoformat``.
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M",
)

_NAN_STRINGS = {"", "nan", "none", "null", "#n/a", "#div/0!", "#ref!", "#value!"}


def _norm_header(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def _parse_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    s = value.strip()
    if s.lower() in _NAN_STRINGS:
        return None
    try:
        f = float(s)
    except (ValueError, TypeError):
        return None
    # Reject NaN / inf that float() happily parses.
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    s = value.strip()
    if s == "" or s.lower() in _NAN_STRINGS:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_direction(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = value.strip().lower()
    if s in ("long", "buy"):
        return "long"
    if s in ("short", "sell"):
        return "short"
    return None


def parse_csv(data: bytes) -> tuple[list[ParsedTrade], int]:
    """Parse ``data`` (comma-delimited CSV) into (trades, skipped_count).

    Raises ``ValueError`` if the header contains none of the known columns.
    """
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))

    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("empty CSV: no header row")

    norm = [_norm_header(h) for h in header]
    if not (_KNOWN_COLUMNS & set(norm)):
        raise ValueError(
            "CSV header has no known Hadrian² columns "
            f"(expected at least one of: {sorted(_KNOWN_COLUMNS)})"
        )

    # header column name -> index
    idx = {name: i for i, name in enumerate(norm)}

    def cell(row: list[str], name: str) -> Optional[str]:
        i = idx.get(name)
        if i is None or i >= len(row):
            return None
        return row[i]

    trades: list[ParsedTrade] = []
    skipped = 0

    for row in reader:
        if not any(c.strip() for c in row):
            skipped += 1
            continue

        trade_datetime = _parse_datetime(cell(row, "entry_time"))
        direction = _parse_direction(cell(row, "direction"))
        entry = _parse_number(cell(row, "entry_price"))
        sl = _parse_number(cell(row, "sl_price"))
        exit_ = _parse_number(cell(row, "exit_price"))
        r_value = _parse_number(cell(row, "net_r"))
        timeframe = None
        tf_raw = cell(row, "timeframe")
        if tf_raw is not None and tf_raw.strip():
            timeframe = tf_raw.strip()

        parseable = (
            trade_datetime,
            direction,
            entry,
            sl,
            exit_,
            r_value,
            timeframe,
        )
        if all(v is None for v in parseable):
            skipped += 1
            continue

        trades.append(
            ParsedTrade(
                trade_datetime=trade_datetime,
                timeframe=timeframe,
                entry=entry,
                sl=sl,
                exit=exit_,
                direction=direction,
                r_value=r_value,
                win_loss=derive_win_loss(r_value),
            )
        )

    return trades, skipped
