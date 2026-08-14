"""DB-free unit tests for the pure quant service (Phase 5, T5).

All expected values are hand-computed in the comments so the tests double as a
specification. Run from backend/:  .venv/bin/python -m pytest tests/test_quant.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import pytest

from app.services.quant import (
    monte_carlo,
    percentile_inc,
    topography,
    walk_forward,
)

APPROX = dict(rel=1e-9, abs=1e-12)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

@dataclass
class Trade:
    """Minimal TradeLike stand-in for walk_forward."""

    r_value: Optional[float] = None
    trade_datetime: Optional[datetime] = None
    win_loss: Optional[str] = None
    entry: Optional[float] = 100.0


def _pt(x, y, value):
    return {"x": x, "y": y, "value": value}


def _cell(topo, x, y):
    for c in topo["cells"]:
        if c["x"] == x and c["y"] == y:
            return c
    raise AssertionError(f"cell ({x},{y}) not found")


# --------------------------------------------------------------------------- #
# Topography: 3x3 grid, exact neighbour statistics
# --------------------------------------------------------------------------- #
#
# Values laid out as V[x][y], x_values = y_values = [0, 1, 2]:
#
#   y=2 |  7   8   9
#   y=1 |  4   5   6
#   y=0 |  1   2   3
#         x=0 x=1 x=2
#
GRID_3x3 = [
    _pt(0, 0, 1), _pt(1, 0, 2), _pt(2, 0, 3),
    _pt(0, 1, 4), _pt(1, 1, 5), _pt(2, 1, 6),
    _pt(0, 2, 7), _pt(1, 2, 8), _pt(2, 2, 9),
]


def test_topography_axes_and_cell_count():
    topo = topography("tp", "sl", GRID_3x3)
    assert topo["param_x"] == "tp"
    assert topo["param_y"] == "sl"
    assert topo["x_values"] == [0, 1, 2]
    assert topo["y_values"] == [0, 1, 2]
    assert len(topo["cells"]) == 9


def test_topography_center_eight_neighbors():
    # Center (1,1)=5 has all 8 others as neighbours: [1,2,3,4,6,7,8,9]
    #   min 1, max 9, mean 40/8 = 5.0
    c = _cell(topography("tp", "sl", GRID_3x3), 1, 1)
    assert c["n_neighbors"] == 8
    assert c["neighbor_min"] == 1
    assert c["neighbor_max"] == 9
    assert c["neighbor_mean"] == pytest.approx(5.0, **APPROX)


def test_topography_edge_five_neighbors():
    # Edge (1,0)=2 neighbours: (0,0)1,(2,0)3,(0,1)4,(1,1)5,(2,1)6
    #   n 5, min 1, max 6, mean 19/5 = 3.8
    c = _cell(topography("tp", "sl", GRID_3x3), 1, 0)
    assert c["n_neighbors"] == 5
    assert c["neighbor_min"] == 1
    assert c["neighbor_max"] == 6
    assert c["neighbor_mean"] == pytest.approx(3.8, **APPROX)


def test_topography_corner_three_neighbors():
    # Corner (0,0)=1 neighbours: (1,0)2,(0,1)4,(1,1)5
    #   n 3, min 2, max 5, mean 11/3
    c = _cell(topography("tp", "sl", GRID_3x3), 0, 0)
    assert c["n_neighbors"] == 3
    assert c["neighbor_min"] == 2
    assert c["neighbor_max"] == 5
    assert c["neighbor_mean"] == pytest.approx(11 / 3, **APPROX)


def test_topography_aggregates_full_grid():
    topo = topography("tp", "sl", GRID_3x3)
    # all nine values > 0
    assert topo["pct_positive"] == pytest.approx(1.0, **APPROX)
    # max value 9 at (2,2)
    assert topo["best"] == {"x": 2, "y": 2, "value": 9}


# --------------------------------------------------------------------------- #
# Topography: gap (missing cell) must not be a neighbour nor invented
# --------------------------------------------------------------------------- #

def test_topography_gap_cell():
    # Same 3x3 but the centre (1,1) is absent. Axes stay [0,1,2] (x=1/y=1 still
    # occur elsewhere) but no phantom (1,1) cell is created.
    pts = [p for p in GRID_3x3 if not (p["x"] == 1 and p["y"] == 1)]
    topo = topography("tp", "sl", pts)
    assert topo["x_values"] == [0, 1, 2]
    assert topo["y_values"] == [0, 1, 2]
    assert len(topo["cells"]) == 8
    with pytest.raises(AssertionError):
        _cell(topo, 1, 1)

    # Corner (0,0)=1 now only sees (1,0)2 and (0,1)4 (the (1,1) neighbour gone)
    #   n 2, min 2, max 4, mean 3
    c00 = _cell(topo, 0, 0)
    assert c00["n_neighbors"] == 2
    assert c00["neighbor_min"] == 2
    assert c00["neighbor_max"] == 4
    assert c00["neighbor_mean"] == pytest.approx(3.0, **APPROX)

    # Edge (1,0)=2 loses the missing (1,1): [1,3,4,6] -> n 4, mean 3.5
    c10 = _cell(topo, 1, 0)
    assert c10["n_neighbors"] == 4
    assert c10["neighbor_min"] == 1
    assert c10["neighbor_max"] == 6
    assert c10["neighbor_mean"] == pytest.approx(3.5, **APPROX)


# --------------------------------------------------------------------------- #
# Topography: robust_best (plateau) differs from best (spike)
# --------------------------------------------------------------------------- #

def test_topography_robust_best_prefers_plateau():
    # V[x][y], x_values=y_values=[0,1,2]:
    #   y=2 |  6   6   2
    #   y=1 |  6   6   2
    #   y=0 |  2   2  10
    # Spike 10 at (2,0) is the best; the (0,2) corner sits inside the 6-plateau
    # (all three neighbours are 6) -> floor 6, the unique max floor.
    pts = [
        _pt(0, 0, 2), _pt(1, 0, 2), _pt(2, 0, 10),
        _pt(0, 1, 6), _pt(1, 1, 6), _pt(2, 1, 2),
        _pt(0, 2, 6), _pt(1, 2, 6), _pt(2, 2, 2),
    ]
    topo = topography("tp", "sl", pts)
    assert topo["best"] == {"x": 2, "y": 0, "value": 10}
    assert topo["robust_best"] == {"x": 0, "y": 2, "value": 6, "floor": 6}
    # pct_positive: all nine > 0
    assert topo["pct_positive"] == pytest.approx(1.0, **APPROX)


def test_topography_pct_positive_partial():
    # 2x2 with two positive, one zero, one negative -> 2/4 = 0.5
    pts = [_pt(0, 0, 1.0), _pt(1, 0, -1.0), _pt(0, 1, 0.0), _pt(1, 1, 2.0)]
    topo = topography("tp", "sl", pts)
    assert topo["pct_positive"] == pytest.approx(0.5, **APPROX)


# --------------------------------------------------------------------------- #
# Topography: 1xN grid and empty input
# --------------------------------------------------------------------------- #

def test_topography_one_row_grid():
    # y_values = [0] (single row), x_values = [0,1,2,3]
    #   values 1,2,3,4
    pts = [_pt(0, 0, 1), _pt(1, 0, 2), _pt(2, 0, 3), _pt(3, 0, 4)]
    topo = topography("tp", "sl", pts)
    assert topo["x_values"] == [0, 1, 2, 3]
    assert topo["y_values"] == [0]
    # (0,0) sees only (1,0)=2
    assert _cell(topo, 0, 0)["n_neighbors"] == 1
    assert _cell(topo, 0, 0)["neighbor_min"] == 2
    # (1,0) sees (0,0)=1 and (2,0)=3
    assert _cell(topo, 1, 0)["n_neighbors"] == 2
    # floors: (0,0)1,(1,0)1,(2,0)min(3,2)=2,(3,0)min(4,3)=3 -> robust (3,0)
    assert topo["best"] == {"x": 3, "y": 0, "value": 4}
    assert topo["robust_best"] == {"x": 3, "y": 0, "value": 4, "floor": 3}


def test_topography_isolated_single_cell():
    # Single point -> no neighbours; floor falls back to the value itself.
    topo = topography("tp", "sl", [_pt(0.5, 0.1, 0.27)])
    c = _cell(topo, 0.5, 0.1)
    assert c["n_neighbors"] == 0
    assert c["neighbor_min"] is None
    assert c["neighbor_mean"] is None
    assert topo["best"]["value"] == 0.27
    assert topo["robust_best"] == {"x": 0.5, "y": 0.1, "value": 0.27, "floor": 0.27}


def test_topography_empty_points():
    topo = topography("tp", "sl", [])
    assert topo["x_values"] == []
    assert topo["y_values"] == []
    assert topo["cells"] == []
    assert topo["pct_positive"] is None
    assert topo["best"] is None
    assert topo["robust_best"] is None


def test_topography_categorical_axis_first_appearance():
    # Non-numeric x keeps first-appearance order (not sorted); numeric y sorted.
    pts = [
        _pt("wide", 0.2, 1.0), _pt("tight", 0.2, 2.0),
        _pt("wide", 0.1, 3.0), _pt("tight", 0.1, 4.0),
    ]
    topo = topography("tp_type", "sl", pts)
    assert topo["x_values"] == ["wide", "tight"]   # order of first appearance
    assert topo["y_values"] == [0.1, 0.2]          # numeric ascending


# --------------------------------------------------------------------------- #
# Walk-forward: 18 monthly trades starting November 2023 (crosses year end)
# --------------------------------------------------------------------------- #
#
# One trade per month on the 15th, Nov-2023 .. Apr-2025 (18 trades).
# R by month index m0..m17:
#   Nov23 1, Dec23 2, Jan24 -1, Feb24 3, Mar24 0, Apr24 -2,
#   May24 1, Jun24 2,  Jul24 -1, Aug24 4, Sep24 0, Oct24 -2,
#   Nov24 1, Dec24 2,  Jan25 3,  Feb25 -1, Mar25 0, Apr25 1
#
# is_months=6, oos_months=3, step=oos_months=3, t0 = 2023-11-01, last = 2025-04-15.
# Windows generated while is_end <= last:
#   k0: IS [2023-11,2024-05) m0..m5 [1,2,-1,3,0,-2] ev 3/6=0.5
#       OOS [2024-05,2024-08) m6..m8 [1,2,-1] ev 2/3
#   k1: IS [2024-02,2024-08) m3..m8 [3,0,-2,1,2,-1] ev 3/6=0.5
#       OOS [2024-08,2024-11) m9..m11 [4,0,-2] ev 2/3
#   k2: IS [2024-05,2024-11) m6..m11 [1,2,-1,4,0,-2] ev 4/6
#       OOS [2024-11,2025-02) m12..m14 [1,2,3] ev 2.0
#   k3: IS [2024-08,2025-02) m9..m14 [4,0,-2,1,2,3] ev 8/6
#       OOS [2025-02,2025-05) m15..m17 [-1,0,1] ev 0.0
#   k4: is_end 2025-05 > last -> stop.  => 4 windows.
#
_MONTHS = [
    (2023, 11, 1.0), (2023, 12, 2.0), (2024, 1, -1.0), (2024, 2, 3.0),
    (2024, 3, 0.0), (2024, 4, -2.0), (2024, 5, 1.0), (2024, 6, 2.0),
    (2024, 7, -1.0), (2024, 8, 4.0), (2024, 9, 0.0), (2024, 10, -2.0),
    (2024, 11, 1.0), (2024, 12, 2.0), (2025, 1, 3.0), (2025, 2, -1.0),
    (2025, 3, 0.0), (2025, 4, 1.0),
]
MONTHLY = [Trade(r_value=r, trade_datetime=datetime(y, m, 15)) for (y, m, r) in _MONTHS]


def test_walk_forward_windows_exact():
    wf = walk_forward(MONTHLY, is_months=6, oos_months=3)
    assert wf["step_months"] == 3          # default = oos_months
    assert wf["n_dated_trades"] == 18
    assert wf["n_windows"] == 4
    assert wf["n_windows_evaluated"] == 4  # every window has n_oos=3 >= 1

    w = wf["windows"]
    assert w[0]["is_start"] == date(2023, 11, 1)
    assert w[0]["is_end"] == date(2024, 5, 1)
    assert w[0]["oos_start"] == date(2024, 5, 1)
    assert w[0]["oos_end"] == date(2024, 8, 1)

    assert [x["n_is"] for x in w] == [6, 6, 6, 6]
    assert [x["n_oos"] for x in w] == [3, 3, 3, 3]

    assert w[0]["is_ev"] == pytest.approx(0.5, **APPROX)
    assert w[1]["is_ev"] == pytest.approx(0.5, **APPROX)
    assert w[2]["is_ev"] == pytest.approx(4 / 6, **APPROX)
    assert w[3]["is_ev"] == pytest.approx(8 / 6, **APPROX)

    assert w[0]["oos_ev"] == pytest.approx(2 / 3, **APPROX)
    assert w[1]["oos_ev"] == pytest.approx(2 / 3, **APPROX)
    assert w[2]["oos_ev"] == pytest.approx(2.0, **APPROX)
    assert w[3]["oos_ev"] == pytest.approx(0.0, **APPROX)


def test_walk_forward_aggregates():
    wf = walk_forward(MONTHLY, is_months=6, oos_months=3)
    # oos_ev = [2/3, 2/3, 2, 0]; positive in 3 of 4 -> 0.75
    assert wf["pct_positive"] == pytest.approx(0.75, **APPROX)
    # mean = (2/3+2/3+2+0)/4 = (10/3)/4 = 5/6
    assert wf["oos_ev_mean"] == pytest.approx(5 / 6, **APPROX)
    # sample std (ddof=1) over [2/3,2/3,2,0] = sqrt(19/27)
    assert wf["oos_ev_std"] == pytest.approx((19 / 27) ** 0.5, **APPROX)


def test_walk_forward_step_months_override():
    # step_months=6 -> non-overlapping-by-6 windows: k0 and k1 only.
    #   k0 IS [2023-11,2024-05) ; k1 IS [2024-05,2024-11) ; k2 is_end 2025-05>last
    wf = walk_forward(MONTHLY, is_months=6, oos_months=3, step_months=6)
    assert wf["step_months"] == 6
    assert wf["n_windows"] == 2
    w = wf["windows"]
    assert w[0]["is_start"] == date(2023, 11, 1)
    assert w[1]["is_start"] == date(2024, 5, 1)
    assert w[1]["oos_ev"] == pytest.approx(2.0, **APPROX)  # m12..m14 [1,2,3]


def test_walk_forward_min_oos_excludes_windows():
    # min_oos_trades=4 -> every window (n_oos=3) is excluded from the denominator
    wf = walk_forward(MONTHLY, is_months=6, oos_months=3, min_oos_trades=4)
    assert wf["n_windows"] == 4
    assert wf["n_windows_evaluated"] == 0
    assert wf["pct_positive"] is None       # empty denominator
    assert wf["oos_ev_mean"] is None
    assert wf["oos_ev_std"] is None


def test_walk_forward_ignores_undated_and_no_r():
    # A trade without a datetime and one without R must be dropped silently.
    trades = list(MONTHLY) + [
        Trade(r_value=99.0, trade_datetime=None),
        Trade(r_value=None, trade_datetime=datetime(2024, 6, 20)),
    ]
    wf = walk_forward(trades, is_months=6, oos_months=3)
    assert wf["n_dated_trades"] == 18       # only the fully-populated monthlies
    assert wf["n_windows"] == 4


def test_walk_forward_too_few_dated_trades():
    wf = walk_forward([Trade(r_value=1.0, trade_datetime=datetime(2024, 1, 1))])
    assert wf["n_windows"] == 0
    assert wf["windows"] == []
    assert wf["pct_positive"] is None
    assert wf["n_dated_trades"] == 1


def test_walk_forward_std_none_below_two_evaluated():
    # A trade span that yields exactly one window -> std undefined, mean defined.
    # 7 monthly trades Jan-Jul 2024: is=6, oos=3, step=3.
    #   k0 IS [2024-01,2024-07) 6 trades, OOS [2024-07,2024-10) only Jul -> n_oos 1
    #   k1 is_end 2024-10 > last (2024-07-15) -> stop. 1 window.
    trades = [
        Trade(r_value=1.0, trade_datetime=datetime(2024, m, 15)) for m in range(1, 8)
    ]
    wf = walk_forward(trades, is_months=6, oos_months=3)
    assert wf["n_windows"] == 1
    assert wf["n_windows_evaluated"] == 1
    assert wf["pct_positive"] == pytest.approx(1.0, **APPROX)
    assert wf["oos_ev_mean"] == pytest.approx(1.0, **APPROX)
    assert wf["oos_ev_std"] is None


# --------------------------------------------------------------------------- #
# Monte-Carlo
# --------------------------------------------------------------------------- #

R_MIX = [2.0, -1.0, 1.5, -1.0, 3.0, -0.5, 0.5, -2.0]


def test_monte_carlo_seed_determinism():
    a = monte_carlo(R_MIX, n_iterations=200, seed=7)
    b = monte_carlo(R_MIX, n_iterations=200, seed=7)
    assert a == b                                  # fully reproducible
    c = monte_carlo(R_MIX, n_iterations=200, seed=8)
    assert c["ev_p50"] != a["ev_p50"]              # different seed -> different draw


def test_monte_carlo_output_shape_and_horizon():
    mc = monte_carlo(R_MIX, n_iterations=100, seed=42)
    assert mc["horizon"] == len(R_MIX)             # default horizon = n trades
    for k in ("ev_p5", "ev_p25", "ev_p50", "ev_p75", "ev_p95", "p_ev_positive"):
        assert mc[k] is not None
    # percentiles are monotonically non-decreasing
    ps = [mc["ev_p5"], mc["ev_p25"], mc["ev_p50"], mc["ev_p75"], mc["ev_p95"]]
    assert ps == sorted(ps)
    assert 0.0 <= mc["p_ev_positive"] <= 1.0

    mc2 = monte_carlo(R_MIX, n_iterations=100, seed=42, horizon=5)
    assert mc2["horizon"] == 5
    assert mc2["equity_fan"]["steps"] == [1, 2, 3, 4, 5]


def test_monte_carlo_degenerate_all_equal():
    mc = monte_carlo([1.5, 1.5, 1.5], n_iterations=300, seed=1)
    # every bootstrap mean is exactly 1.5 -> all EV percentiles == 1.5
    for k in ("ev_p5", "ev_p25", "ev_p50", "ev_p75", "ev_p95"):
        assert mc[k] == pytest.approx(1.5, **APPROX)
    assert mc["p_ev_positive"] == 1.0              # 1.5 > 0 always
    # histogram still sums to n_iterations despite zero-width range
    assert sum(b["count"] for b in mc["ev_histogram"]) == 300


def test_monte_carlo_degenerate_negative_p_zero():
    mc = monte_carlo([-2.0, -2.0], n_iterations=50, seed=1)
    assert mc["ev_p50"] == pytest.approx(-2.0, **APPROX)
    assert mc["p_ev_positive"] == 0.0              # never positive


def test_monte_carlo_empty_input():
    mc = monte_carlo([], n_iterations=100)
    assert mc["horizon"] == 0
    for k in ("ev_p5", "ev_p25", "ev_p50", "ev_p75", "ev_p95", "p_ev_positive"):
        assert mc[k] is None
    assert mc["ev_histogram"] == []
    assert mc["equity_fan"]["steps"] == []
    assert mc["equity_fan"]["p50"] == []


def test_monte_carlo_equity_fan_lengths():
    mc = monte_carlo(R_MIX, n_iterations=100, seed=42)
    fan = mc["equity_fan"]
    steps = fan["steps"]
    # short horizon (<=250): every trade index present, 1-based, monotone
    assert steps == list(range(1, len(R_MIX) + 1))
    assert steps[0] == 1 and steps[-1] == len(R_MIX)
    for k in ("p5", "p25", "p50", "p75", "p95"):
        assert len(fan[k]) == len(steps)
    # per-step percentiles stay ordered
    for i in range(len(steps)):
        row = [fan["p5"][i], fan["p25"][i], fan["p50"][i], fan["p75"][i], fan["p95"][i]]
        assert row == sorted(row)


def test_monte_carlo_equity_fan_downsampling():
    # horizon 1000 (>250) -> <=250 steps, first=1, last=1000, strictly increasing
    mc = monte_carlo([1.0, -1.0], n_iterations=30, seed=42, horizon=1000)
    steps = mc["equity_fan"]["steps"]
    assert len(steps) <= 250
    assert steps[0] == 1
    assert steps[-1] == 1000
    assert all(steps[i] < steps[i + 1] for i in range(len(steps) - 1))
    for k in ("p5", "p25", "p50", "p75", "p95"):
        assert len(mc["equity_fan"][k]) == len(steps)


def test_monte_carlo_histogram_bins():
    mc = monte_carlo(R_MIX, n_iterations=500, seed=42)
    hist = mc["ev_histogram"]
    assert len(hist) == 30                          # exactly 30 bins
    assert sum(b["count"] for b in hist) == 500     # every EV lands in a bin
    # contiguous, ascending bin edges spanning the observed EV range
    assert hist[0]["bin_start"] <= hist[0]["bin_end"]
    for i in range(len(hist) - 1):
        assert hist[i]["bin_end"] == pytest.approx(hist[i + 1]["bin_start"], **APPROX)


# --------------------------------------------------------------------------- #
# PERCENTILE.INC reuse: hand-computed 4-value case
# --------------------------------------------------------------------------- #

def test_percentile_inc_four_values():
    # sorted [10, 20, 30, 40], n=4, rank = p*(n-1) = p*3
    #   p05: 0.15 -> 10 + 0.15*10 = 11.5
    #   p25: 0.75 -> 10 + 0.75*10 = 17.5
    #   p50: 1.5  -> 20 + 0.5*10  = 25.0
    #   p75: 2.25 -> 30 + 0.25*10 = 32.5
    #   p95: 2.85 -> 30 + 0.85*10 = 38.5
    data = [40.0, 10.0, 30.0, 20.0]
    assert percentile_inc(data, 0.05) == pytest.approx(11.5, **APPROX)
    assert percentile_inc(data, 0.25) == pytest.approx(17.5, **APPROX)
    assert percentile_inc(data, 0.50) == pytest.approx(25.0, **APPROX)
    assert percentile_inc(data, 0.75) == pytest.approx(32.5, **APPROX)
    assert percentile_inc(data, 0.95) == pytest.approx(38.5, **APPROX)
