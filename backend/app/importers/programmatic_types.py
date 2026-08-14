"""Shared dataclasses for the two programmatic backtest parsers (Phase 5, D2).

Pure and DB-free. Both ``app/importers/hadrian2.py`` and
``app/importers/hadrian_engine.py`` return lists of
:class:`ParsedProgrammaticSystem`; the import service
(``app/services/import_service.py``) persists them. Mirrors the shape of the
xlsx importer's :class:`~app.importers.xlsx.ParsedTab`, extended with the
parameter-sweep grids (:class:`ParsedSweep`) that only the programmatic sources
carry.

Trades reuse :class:`~app.importers.xlsx.ParsedTrade` verbatim, so the metric
engine and persistence layer treat manual and programmatic trades identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.importers.xlsx import ParsedTrade  # re-exported for parser modules

__all__ = ["ParsedTrade", "ParsedSweep", "ParsedProgrammaticSystem"]


@dataclass
class ParsedSweep:
    """One parameter-sweep grid (D3).

    ``points`` is a list of JSONB-ready dicts with the fixed shape
    ``{"x", "y", "value", "net_ev", "n_trades", "low_confidence",
    "insufficient_sample"}``. ``value`` always carries the primary metric
    (``metric``) so the quant service stays metric-agnostic. Axis values are
    left in CSV order here; ordering (numeric asc / first-appearance) is applied
    downstream by the quant service.
    """

    label: str
    param_x: str
    param_y: str
    metric: str = "oos_net_ev"
    points: list[dict] = field(default_factory=list)


@dataclass
class ParsedProgrammaticSystem:
    """A programmatic system ready for upsert (provenance='programmatic')."""

    name: str
    source_engine: str  # "hadrian2" | "hadrian_engine"
    timeframe: Optional[str] = None
    # Traded asset, set only where the source evidences one. None means no
    # evidence; the import then applies the default (app/importers/assets.py).
    asset: Optional[str] = None
    entry_rule: Optional[str] = None
    sl_rule: Optional[str] = None
    tp_rule: Optional[str] = None
    notes: Optional[str] = None
    reported_metrics: Optional[dict] = None
    parse_status: str = "incomplete"  # "complete" | "incomplete" | "skipped"
    message: Optional[str] = None
    trades: list[ParsedTrade] = field(default_factory=list)
    sweeps: list[ParsedSweep] = field(default_factory=list)
