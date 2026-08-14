"""Derive the traded asset from the backtest sources.

Pure and database-free. ``systems.asset`` drives lot size and maximum leverage
in the risk calculator, so a missing asset silently falls back to DEFAULT
granularity. The three sources support that derivation to very different
degrees:

- **xlsx (manual systems):** no dedicated header field. In some tabs the trade
  log column headed ``Timeframe`` holds a ticker (``BTC``, ``XMR``, ``DOT``,
  ``BTCUSDT.P``) instead of a timeframe. In every other tab the same column
  holds an actual timeframe (``H1``, ``M15``, ``D / H1``, ``00:15:00``) or a
  session label (``U.S./New York``). The column is therefore ambiguous and is
  classified conservatively — see :func:`asset_candidate_from_cell`.
- **Hadrian Engine:** ``results.xlsx`` has a real ``Symbol`` column. The asset
  is the symbol of the already-selected best config, taken from the same row
  the metrics and trades come from. No separate selection rule.
- **Hadrian²:** no symbol column. The base run is BTC; ``audit_master.csv``
  carries ETH/SOL/DOGE only as cross-market counter-checks (``xmkt_*_oos_ev``).

With no evidence at all, BTC applies as a documented default assumption. An
*unknown* ticker is never quietly mapped to BTC — it is carried through
verbatim and logged.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Tickers for which ``asset_settings`` holds real venue values. Anything else
# counts as unknown -> carried through verbatim and logged.
KNOWN_ASSETS: frozenset[str] = frozenset(
    {"BTC", "ETH", "SOL", "DOT", "XMR", "AVAX", "LINK", "DOGE"}
)

# Default assumption when there is no evidence.
DEFAULT_ASSET = "BTC"

# Base market of the Hadrian² runs; cross-market columns are counter-checks only.
HADRIAN2_BASE_ASSET = "BTC"

# Quote currencies that may be appended to the base ticker.
_QUOTES = ("USDT", "USDC", "BUSD", "USDP", "USD")

# Perp suffix: ".P" / "-PERP" / "PERP", with or without a separator.
# Deliberately NOT a bare "P", which would mangle "XRP" into "XR".
_PERP_RE = re.compile(r"(?:[.\-_/ ]P|[.\-_/ ]?PERP)$")

# Tokens in the ambiguous xlsx column that are definitely NOT assets.
_NON_ASSET_TOKENS = frozenset(
    {
        "D", "W", "H", "M", "S", "TF", "NA", "N",
        "DAILY", "WEEKLY", "MONTHLY", "HOURLY",
        "MIN", "MINS", "MINUTE", "HOUR", "DAY", "WEEK", "MONTH",
        "LONG", "SHORT", "WIN", "LOSS", "ZONE", "NONE",
    }
)

_TICKER_RE = re.compile(r"[A-Z][A-Z0-9]{1,9}")
_BARE_TICKER_RE = re.compile(r"[A-Z]{2,5}")


def _strip_symbol_suffix(symbol: str) -> tuple[str, bool]:
    """``BTCUSDT.P`` -> ``("BTC", True)``; ``BTC`` -> ``("BTC", False)``.

    The flag reports whether an exchange suffix was stripped at all, which is
    what separates an unambiguous symbol string from a bare token.
    """
    s = symbol.strip().upper()
    s = s.split(":")[-1]  # "BINANCE:BTCUSDT.P" -> "BTCUSDT.P"
    stripped = False

    without_perp = _PERP_RE.sub("", s)
    if without_perp != s:
        stripped = True
        s = without_perp

    s = s.replace("/", "").replace("-", "").replace("_", "").strip()

    for quote in _QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            s = s[: -len(quote)]
            stripped = True
            break

    return s, stripped


def normalize_ticker(raw) -> Optional[str]:
    """Raw ticker -> normalized base ticker (upper-case, suffix removed).

    ``BTCUSDT.P``/``BTCUSDT``/``btc`` -> ``BTC``; ``ETHUSDT.P`` -> ``ETH``.
    Values that do not look like tickers -> ``None``.
    """
    if raw is None:
        return None
    base, _ = _strip_symbol_suffix(str(raw))
    if not base or not _TICKER_RE.fullmatch(base):
        return None
    return base


def asset_candidate_from_cell(raw) -> Optional[str]:
    """Classify one cell of the ambiguous xlsx ``Timeframe`` column.

    Only what is unambiguously a ticker is accepted:

    1. An exchange symbol carrying a quote/perp suffix (``BTCUSDT.P``) — always.
    2. A bare, fully upper-case word of 2-5 letters that is neither a timeframe
       nor a domain term (``BTC``, ``XMR``, ``DOT``).

    Everything else (``H1``, ``M15``, ``D / H1``, ``00:15:00``,
    ``U.S./New York``, ``Asia``) -> ``None``.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    base, stripped = _strip_symbol_suffix(s)
    if stripped:
        return base if _TICKER_RE.fullmatch(base) else None

    # Bare token: judged strictly, because the column mostly carries timeframes.
    if s != s.upper():  # "Asia", "New York", "Daily" -> not a ticker
        return None
    if not _BARE_TICKER_RE.fullmatch(s):  # digits/punctuation -> a timeframe
        return None
    if s in _NON_ASSET_TOKENS:
        return None
    return s


def is_known(asset: Optional[str]) -> bool:
    return asset is not None and asset in KNOWN_ASSETS


def _log_unknown(asset: str, source: str, context: Optional[str]) -> None:
    if not is_known(asset):
        logger.warning(
            "Unknown asset ticker %r (%s, %s) — carried through verbatim, "
            "no silent BTC fallback.",
            asset,
            source,
            context or "?",
        )


def derive_asset_from_timeframe_cells(
    values: Iterable, context: Optional[str] = None
) -> Optional[str]:
    """Asset from the values of one tab's xlsx ``Timeframe`` column.

    Majority vote across every cell classified as a ticker; no candidate at all
    -> ``None``, and the caller then applies the default.
    """
    counter: Counter[str] = Counter()
    for value in values:
        candidate = asset_candidate_from_cell(value)
        if candidate:
            counter[candidate] += 1
    if not counter:
        return None
    if len(counter) > 1:
        logger.warning(
            "Ambiguous asset column (%s): %s — most frequent value wins.",
            context or "?",
            dict(counter),
        )
    asset = counter.most_common(1)[0][0]
    _log_unknown(asset, "xlsx Timeframe column", context)
    return asset


def derive_asset_from_symbol(symbol, context: Optional[str] = None) -> Optional[str]:
    """Asset from a real ``Symbol`` column (Hadrian Engine best config)."""
    asset = normalize_ticker(symbol)
    if asset is None:
        return None
    _log_unknown(asset, "Symbol column", context)
    return asset


def resolve_asset(derived: Optional[str], context: Optional[str] = None) -> str:
    """The evidenced asset, or the documented default assumption (BTC)."""
    if derived:
        return derived
    logger.info(
        "No asset evidence for %s — defaulting to %s.", context or "?", DEFAULT_ASSET
    )
    return DEFAULT_ASSET
