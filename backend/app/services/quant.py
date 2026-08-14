"""Pure, DB-free quant analytics for Hadrian3 (Phase 5, D4).

Three stdlib-only functions, no numpy/scipy and no ORM knowledge:

* ``topography``   — turns a flat list of sweep points into a 2D grid with
  Queen-adjacency neighbour statistics per cell plus plateau-oriented
  aggregates (``best`` / ``robust_best`` / ``pct_positive``).
* ``walk_forward`` — rolling in-sample / out-of-sample windows over a trade
  set, with hand-written month arithmetic and ddof=1 dispersion.
* ``monte_carlo``  — seeded bootstrap of the R distribution, producing EV
  percentiles, an EV histogram and a cumulative equity fan.

The percentile logic is the Phase-3 ``PERCENTILE.INC`` implementation from
``app.services.metrics`` — reused verbatim (not duplicated). Everything here is
deterministic given its inputs (Monte-Carlo via an explicit ``random.Random``
seed); no DB, no network, no wall-clock.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any, List, Optional, Sequence

from app.services.metrics import TradeLike, _percentile_inc

# Re-export under a public name so callers/tests do not reach into metrics'
# private helper. Same PERCENTILE.INC / numpy-"linear" interpolation.
percentile_inc = _percentile_inc

__all__ = ["topography", "walk_forward", "monte_carlo", "percentile_inc"]

_PCTS = (0.05, 0.25, 0.50, 0.75, 0.95)


def _is_num(v: Any) -> bool:
    """True for a real int/float value (bool excluded, None excluded)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# --------------------------------------------------------------------------- #
# Topography
# --------------------------------------------------------------------------- #

def _ordered_axis(raw: Sequence[Any]) -> List[Any]:
    """Axis order per D3: numeric ascending, else first-appearance order.

    ``raw`` is the sequence of a coordinate across all points (input order).
    Duplicates are collapsed keeping first appearance; if every distinct value
    is numeric the axis is sorted ascending, otherwise categorical order is
    preserved.
    """
    seen: List[Any] = []
    for v in raw:
        if v not in seen:
            seen.append(v)
    if seen and all(_is_num(v) for v in seen):
        return sorted(seen)
    return seen


def topography(param_x: str, param_y: str, points: Sequence[dict]) -> dict:
    """Build a 2D grid with Queen-adjacency neighbour stats and aggregates.

    ``points`` is the JSONB-style list from ``parameter_sweeps`` — each item a
    dict carrying at least ``x``, ``y`` and ``value`` (extra keys such as
    ``net_ev`` / ``n_trades`` are passed through onto the cell untouched).

    Per cell the 8 index-space neighbours (without self, only existing cells
    with a numeric ``value``) yield ``neighbor_min`` / ``neighbor_max`` /
    ``neighbor_mean`` / ``n_neighbors`` (``None``/0 when isolated). Grid
    aggregates: ``pct_positive`` (share of cells with ``value>0``), ``best``
    (max ``value``) and ``robust_best`` (max ``min(value, neighbor_min)`` —
    the flattest high plateau; floor falls back to ``value`` when isolated).
    """
    if not points:
        return {
            "param_x": param_x,
            "param_y": param_y,
            "x_values": [],
            "y_values": [],
            "cells": [],
            "pct_positive": None,
            "best": None,
            "robust_best": None,
        }

    x_values = _ordered_axis([p["x"] for p in points])
    y_values = _ordered_axis([p["y"] for p in points])
    x_index = {v: i for i, v in enumerate(x_values)}
    y_index = {v: i for i, v in enumerate(y_values)}

    # Map grid index position -> numeric value (only cells with a numeric value
    # participate as neighbours; a "gap" is simply an absent key).
    value_at: dict[tuple[int, int], float] = {}
    for p in points:
        if _is_num(p.get("value")):
            value_at[(x_index[p["x"]], y_index[p["y"]])] = float(p["value"])

    cells: List[dict] = []
    for p in points:
        xi, yi = x_index[p["x"]], y_index[p["y"]]
        neigh: List[float] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nv = value_at.get((xi + dx, yi + dy))
                if nv is not None:
                    neigh.append(nv)
        cell = dict(p)
        if neigh:
            cell["neighbor_min"] = min(neigh)
            cell["neighbor_max"] = max(neigh)
            cell["neighbor_mean"] = sum(neigh) / len(neigh)
            cell["n_neighbors"] = len(neigh)
        else:
            cell["neighbor_min"] = None
            cell["neighbor_max"] = None
            cell["neighbor_mean"] = None
            cell["n_neighbors"] = 0
        cells.append(cell)

    numeric_cells = [c for c in cells if _is_num(c.get("value"))]
    pct_positive: Optional[float] = None
    best: Optional[dict] = None
    robust_best: Optional[dict] = None
    if numeric_cells:
        pct_positive = sum(1 for c in numeric_cells if c["value"] > 0) / len(
            numeric_cells
        )

        best_cell = max(numeric_cells, key=lambda c: c["value"])
        best = {"x": best_cell["x"], "y": best_cell["y"], "value": best_cell["value"]}

        def _floor(c: dict) -> float:
            nm = c["neighbor_min"]
            return c["value"] if nm is None else min(c["value"], nm)

        rb = max(numeric_cells, key=_floor)
        robust_best = {
            "x": rb["x"],
            "y": rb["y"],
            "value": rb["value"],
            "floor": _floor(rb),
        }

    return {
        "param_x": param_x,
        "param_y": param_y,
        "x_values": x_values,
        "y_values": y_values,
        "cells": cells,
        "pct_positive": pct_positive,
        "best": best,
        "robust_best": robust_best,
    }


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #

def _month_start(dt: datetime) -> datetime:
    """First instant of the month containing ``dt``."""
    return datetime(dt.year, dt.month, 1)


def _add_months(dt: datetime, n: int) -> datetime:
    """``dt`` (always on day 1) shifted by ``n`` whole months. No day overflow."""
    total = dt.year * 12 + (dt.month - 1) + n
    return dt.replace(year=total // 12, month=total % 12 + 1)


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _stdev_s(values: Sequence[float]) -> Optional[float]:
    """Sample standard deviation (ddof=1); None if fewer than 2 values."""
    n = len(values)
    if n < 2:
        return None
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    return var ** 0.5


def walk_forward(
    trades: Sequence[TradeLike],
    is_months: int = 6,
    oos_months: int = 3,
    step_months: Optional[int] = None,
    min_oos_trades: int = 1,
) -> dict:
    """Rolling IS/OOS windows over dated, numeric-R trades (D4).

    Only trades carrying both ``trade_datetime`` and a numeric ``r_value`` are
    used. The anchor ``t0`` is the month-start of the earliest such trade;
    ``step_months`` defaults to ``oos_months`` (non-overlapping OOS windows).
    Window ``k``: IS ``[t0+k*step, +is_months)``, OOS ``[is_end, +oos_months)``;
    windows are generated while ``is_end <= last trade datetime``.

    ``pct_positive`` is the share of windows with ``oos_ev>0`` among windows
    with ``n_oos >= min_oos_trades`` (denominator ``n_windows_evaluated``);
    ``oos_ev_mean`` / ``oos_ev_std`` (ddof=1) are computed over those evaluated
    windows and are ``None`` below 2 of them. Returns fractions, not percents.
    """
    working = sorted(
        (t for t in trades if t.trade_datetime is not None and t.r_value is not None),
        key=lambda t: t.trade_datetime,
    )
    n_dated = len(working)

    empty = {
        "is_months": is_months,
        "oos_months": oos_months,
        "step_months": oos_months if step_months is None else step_months,
        "min_oos_trades": min_oos_trades,
        "n_windows": 0,
        "n_windows_evaluated": 0,
        "pct_positive": None,
        "oos_ev_mean": None,
        "oos_ev_std": None,
        "n_dated_trades": n_dated,
        "windows": [],
    }
    if n_dated < 2:
        return empty

    step = oos_months if step_months is None else step_months
    t0 = _month_start(working[0].trade_datetime)
    last_dt = working[-1].trade_datetime

    windows: List[dict] = []
    k = 0
    while True:
        is_start = _add_months(t0, k * step)
        is_end = _add_months(is_start, is_months)
        if is_end > last_dt:
            break
        oos_end = _add_months(is_end, oos_months)

        is_r = [
            t.r_value for t in working if is_start <= t.trade_datetime < is_end
        ]
        oos_r = [
            t.r_value for t in working if is_end <= t.trade_datetime < oos_end
        ]
        windows.append(
            {
                "index": k,
                "is_start": is_start.date(),
                "is_end": is_end.date(),
                "oos_start": is_end.date(),
                "oos_end": oos_end.date(),
                "n_is": len(is_r),
                "n_oos": len(oos_r),
                "is_ev": _mean(is_r),
                "oos_ev": _mean(oos_r),
            }
        )
        k += 1

    evaluated = [w for w in windows if w["n_oos"] >= min_oos_trades]
    n_eval = len(evaluated)
    oos_evs = [w["oos_ev"] for w in evaluated]
    pct_positive = (
        sum(1 for ev in oos_evs if ev > 0) / n_eval if n_eval else None
    )

    return {
        "is_months": is_months,
        "oos_months": oos_months,
        "step_months": step,
        "min_oos_trades": min_oos_trades,
        "n_windows": len(windows),
        "n_windows_evaluated": n_eval,
        "pct_positive": pct_positive,
        "oos_ev_mean": _mean(oos_evs),
        "oos_ev_std": _stdev_s(oos_evs),
        "n_dated_trades": n_dated,
        "windows": windows,
    }


# --------------------------------------------------------------------------- #
# Monte-Carlo
# --------------------------------------------------------------------------- #

_HIST_BINS = 30
_MAX_FAN_STEPS = 250


def _empty_monte_carlo() -> dict:
    return {
        "horizon": 0,
        "ev_p5": None,
        "ev_p25": None,
        "ev_p50": None,
        "ev_p75": None,
        "ev_p95": None,
        "p_ev_positive": None,
        "ev_histogram": [],
        "equity_fan": {
            "steps": [],
            "p5": [],
            "p25": [],
            "p50": [],
            "p75": [],
            "p95": [],
        },
    }


def _fan_steps(horizon: int) -> List[int]:
    """1-based trade indices for the equity fan, downsampled to <=250 points.

    First and last index are always included; sampling is uniform in between.
    """
    all_steps = list(range(1, horizon + 1))
    if horizon <= _MAX_FAN_STEPS:
        return all_steps
    positions = sorted(
        {
            round(i * (horizon - 1) / (_MAX_FAN_STEPS - 1))
            for i in range(_MAX_FAN_STEPS)
        }
    )
    return [all_steps[p] for p in positions]


def monte_carlo(
    r_values: Sequence[float],
    n_iterations: int = 1000,
    seed: int = 42,
    horizon: Optional[int] = None,
) -> dict:
    """Seeded bootstrap of the R distribution (D4).

    Each of ``n_iterations`` iterations draws ``horizon or len(r_values)`` R
    values with replacement via ``random.Random(seed)`` and records the
    per-step cumulative R path plus the iteration EV (mean of the draws).

    Returns EV percentiles (PERCENTILE.INC), ``p_ev_positive`` (share of
    iteration EVs > 0), a 30-bin ``ev_histogram`` over the observed EV range,
    and an ``equity_fan`` of per-step p5/p25/p50/p75/p95 across iterations
    (steps downsampled to <=250, first+last kept). Empty input or a
    non-positive horizon returns all-null / empty without raising.
    """
    r_list = [float(r) for r in r_values]
    h = len(r_list) if horizon is None else horizon
    if not r_list or h <= 0 or n_iterations <= 0:
        return _empty_monte_carlo()

    rng = random.Random(seed)
    evs: List[float] = []
    paths: List[List[float]] = []
    for _ in range(n_iterations):
        cum = 0.0
        path: List[float] = []
        for _ in range(h):
            cum += rng.choice(r_list)
            path.append(cum)
        paths.append(path)
        evs.append(cum / h)

    # EV percentiles + P(EV>0)
    ev_pcts = {p: percentile_inc(evs, p) for p in _PCTS}
    p_ev_positive = sum(1 for ev in evs if ev > 0) / len(evs)

    # 30-bin histogram over the observed EV range (top edge folds into last bin)
    lo, hi = min(evs), max(evs)
    width = (hi - lo) / _HIST_BINS
    counts = [0] * _HIST_BINS
    for ev in evs:
        if width == 0:
            idx = 0
        else:
            idx = int((ev - lo) / width)
            idx = max(0, min(idx, _HIST_BINS - 1))
        counts[idx] += 1
    histogram = [
        {
            "bin_start": lo + i * width,
            "bin_end": lo + (i + 1) * width,
            "count": counts[i],
        }
        for i in range(_HIST_BINS)
    ]

    # Equity fan: per selected step, percentiles across iterations
    steps = _fan_steps(h)
    fan: dict[str, List[Any]] = {"steps": steps, "p5": [], "p25": [], "p50": [],
                                 "p75": [], "p95": []}
    key = {0.05: "p5", 0.25: "p25", 0.50: "p50", 0.75: "p75", 0.95: "p95"}
    for s in steps:
        col = [path[s - 1] for path in paths]
        for p in _PCTS:
            fan[key[p]].append(percentile_inc(col, p))

    return {
        "horizon": h,
        "ev_p5": ev_pcts[0.05],
        "ev_p25": ev_pcts[0.25],
        "ev_p50": ev_pcts[0.50],
        "ev_p75": ev_pcts[0.75],
        "ev_p95": ev_pcts[0.95],
        "p_ev_positive": p_ev_positive,
        "ev_histogram": histogram,
        "equity_fan": fan,
    }
