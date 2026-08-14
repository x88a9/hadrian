"""DB-free unit tests for the pure metric service.

Run from backend/:  .venv/bin/python -m pytest tests/test_metrics.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import pytest

from app.services.metrics import (
    _composite_grade,
    _ece_grade,
    _ev_grade,
    _evol_grade,
    _max_drawdown_r,
    _percentile_inc,
    _profit_factor,
    _skewness,
    compute_all,
    compute_metrics,
    derive_win_loss,
    split_trades,
)


@dataclass
class Row:
    """Minimal TradeLike stand-in (duck-typed on the four attributes)."""

    r_value: Optional[float] = None
    trade_datetime: Optional[datetime] = None
    win_loss: Optional[str] = None
    entry: Optional[float] = 100.0


def _dt(day: int) -> datetime:
    return datetime(2024, 1, day)


APPROX = dict(rel=1e-9)


# --------------------------------------------------------------------------- #
# Main hand-computed dataset
# --------------------------------------------------------------------------- #
#
# Six fully-populated trades (entry + datetime + win_loss all set):
#
#   #  R      date        W/L
#   1  +2.0   2024-01-01  win
#   2  -1.0   2024-01-06  loss
#   3  +1.5   2024-01-11  win
#   4  -1.0   2024-01-16  loss
#   5  +3.0   2024-01-21  win
#   6  -0.5   2024-01-31  loss
#
# Hand derivation:
#   total_trades = 6 (all entries set)
#   wins = 3, losses = 3  ->  win_rate = 3/6 = 0.5
#   R = [2, -1, 1.5, -1, 3, -0.5]
#   total_r = 4.0 ;  ev = 4.0/6 = 0.6666666666666666
#   avg_win_r  = (2+1.5+3)/3   =  2.1666666666666665
#   avg_loss_r = (-1-1-0.5)/3  = -0.8333333333333334
#   sample stdev (ddof=1) = sqrt(14.8333.../5) = 1.7224014243685084
#   ece  = ev / stdev = 0.38705649985809176
#   span = 30 days (2024-01-31 - 2024-01-01)
#   evol = ev * (6/30) = 0.13333333333333333
#   composite = 0.4*ev + 0.4*ece + 0.2*evol = 0.44815593327657005
#
# Grades:
#   composite 0.4482 -> C (>=0.3, <0.45)
#   ev_grade on 0.8*ev = 0.5333 -> B (>=0.4, <0.6)
#   ece_grade 0.3871 -> B (>=0.35, <0.5)
#   evol_grade 0.1333 -> C (>=0.07, <0.15)

MAIN = [
    Row(r_value=2.0, trade_datetime=_dt(1), win_loss="win"),
    Row(r_value=-1.0, trade_datetime=_dt(6), win_loss="loss"),
    Row(r_value=1.5, trade_datetime=_dt(11), win_loss="win"),
    Row(r_value=-1.0, trade_datetime=_dt(16), win_loss="loss"),
    Row(r_value=3.0, trade_datetime=_dt(21), win_loss="win"),
    Row(r_value=-0.5, trade_datetime=_dt(31), win_loss="loss"),
]


def test_main_dataset_values():
    m = compute_metrics(MAIN)
    assert m["total_trades"] == 6
    assert m["wins"] == 3
    assert m["losses"] == 3
    assert m["win_rate"] == pytest.approx(0.5, **APPROX)
    assert m["ev"] == pytest.approx(0.6666666666666666, **APPROX)
    assert m["total_r"] == pytest.approx(4.0, **APPROX)
    assert m["avg_win_r"] == pytest.approx(2.1666666666666665, **APPROX)
    assert m["avg_loss_r"] == pytest.approx(-0.8333333333333334, **APPROX)
    assert m["ece"] == pytest.approx(0.38705649985809176, **APPROX)
    assert m["evol"] == pytest.approx(0.13333333333333333, **APPROX)
    assert m["composite_score"] == pytest.approx(0.44815593327657005, **APPROX)
    assert m["span_days"] == pytest.approx(30.0, **APPROX)
    assert m["first_trade_at"] == _dt(1)
    assert m["last_trade_at"] == _dt(31)


def test_main_dataset_phase3_metrics():
    # R = [2, -1, 1.5, -1, 3, -0.5]
    #   gains = 6.5 ; losses = 2.5 -> profit_factor = 2.6
    #   cumulative (chronological) = [2, 1, 2.5, 1.5, 4.5, 4.0]
    #   peaks                       = [2, 2, 2.5, 2.5, 4.5, 4.5]
    #   drawdowns                   = [0, 1,   0,   1,   0, 0.5] -> max_dd = 1.0
    #   romad = total_r / max_dd = 4.0 / 1.0 = 4.0
    #   sorted R = [-1, -1, -0.5, 1.5, 2, 3] (n=6)
    #     p05: rank 0.25 -> -1.0
    #     p25: rank 1.25 -> -1 + 0.25*0.5   = -0.875
    #     p50: rank 2.5  -> -0.5 + 0.5*2.0  =  0.5
    #     p75: rank 3.75 -> 1.5 + 0.75*0.5  =  1.875
    #     p95: rank 4.75 -> 2   + 0.75*1.0  =  2.75
    m = compute_metrics(MAIN)
    assert m["profit_factor"] == pytest.approx(2.6, **APPROX)
    assert m["max_drawdown_r"] == pytest.approx(1.0, **APPROX)
    assert m["romad"] == pytest.approx(4.0, **APPROX)
    assert m["skewness"] == pytest.approx(0.2821380946999299, **APPROX)
    assert m["r_p05"] == pytest.approx(-1.0, **APPROX)
    assert m["r_p25"] == pytest.approx(-0.875, **APPROX)
    assert m["r_p50"] == pytest.approx(0.5, **APPROX)
    assert m["r_p75"] == pytest.approx(1.875, **APPROX)
    assert m["r_p95"] == pytest.approx(2.75, **APPROX)


def test_main_dataset_grades():
    m = compute_metrics(MAIN)
    assert m["composite_grade"] == "C"
    assert m["ev_grade"] == "B"
    assert m["ece_grade"] == "B"
    assert m["evol_grade"] == "C"


# --------------------------------------------------------------------------- #
# Grade-threshold edge cases (private helpers, exact >= / > semantics)
# --------------------------------------------------------------------------- #

def test_composite_grade_thresholds():
    assert _composite_grade(0.6) == "A"
    assert _composite_grade(0.5999999999) == "B"
    assert _composite_grade(0.45) == "B"
    assert _composite_grade(0.4499999999) == "C"
    assert _composite_grade(0.3) == "C"
    assert _composite_grade(0.2999999999) == "D"
    assert _composite_grade(0.15) == "D"
    assert _composite_grade(0.1499999999) == "F"
    assert _composite_grade(-1.0) == "F"
    assert _composite_grade(None) is None


def test_ev_grade_thresholds():
    # grade is evaluated on 0.8 * ev
    assert _ev_grade(1.0) == "A+"       # 0.8
    assert _ev_grade(0.9999999) == "A"  # ~0.79999
    assert _ev_grade(0.75) == "A"       # 0.6
    assert _ev_grade(0.7499999) == "B"
    assert _ev_grade(0.5) == "B"        # 0.4
    assert _ev_grade(0.4999999) == "C"
    assert _ev_grade(0.3125) == "C"     # 0.25
    assert _ev_grade(0.3124999) == "D"
    assert _ev_grade(0.0001) == "D"     # >0
    assert _ev_grade(0.0) == "F"
    assert _ev_grade(-1.0) == "F"
    assert _ev_grade(None) is None


def test_ece_grade_thresholds():
    assert _ece_grade(0.7) == "A+"
    assert _ece_grade(0.6999999) == "A"
    assert _ece_grade(0.5) == "A"
    assert _ece_grade(0.4999999) == "B"
    assert _ece_grade(0.35) == "B"
    assert _ece_grade(0.3499999) == "C"
    assert _ece_grade(0.2) == "C"
    assert _ece_grade(0.1999999) == "D"
    assert _ece_grade(0.0001) == "D"
    assert _ece_grade(0.0) == "F"
    assert _ece_grade(-0.5) == "F"
    assert _ece_grade(None) is None


def test_evol_grade_thresholds():
    assert _evol_grade(0.4) == "A+"
    assert _evol_grade(0.3999999) == "A"
    assert _evol_grade(0.25) == "A"
    assert _evol_grade(0.2499999) == "B"
    assert _evol_grade(0.15) == "B"
    assert _evol_grade(0.1499999) == "C"
    assert _evol_grade(0.07) == "C"
    assert _evol_grade(0.0699999) == "D"
    assert _evol_grade(0.0001) == "D"
    assert _evol_grade(0.0) == "F"
    assert _evol_grade(-0.1) == "F"
    assert _evol_grade(None) is None


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

def test_empty_list():
    m = compute_metrics([])
    assert m["total_trades"] == 0
    assert m["wins"] == 0
    assert m["losses"] == 0
    for key in (
        "win_rate", "ev", "total_r", "avg_win_r", "avg_loss_r", "ece", "evol",
        "composite_score", "composite_grade", "ev_grade", "ece_grade",
        "evol_grade", "first_trade_at", "last_trade_at", "span_days",
    ):
        assert m[key] is None


def test_single_trade_ece_none():
    # <2 R values -> ECE None -> composite None; span 0 -> evol None
    m = compute_metrics([Row(r_value=2.0, trade_datetime=_dt(1), win_loss="win")])
    assert m["total_trades"] == 1
    assert m["ev"] == pytest.approx(2.0, **APPROX)
    assert m["ece"] is None
    assert m["evol"] is None  # single date -> span 0
    assert m["span_days"] == pytest.approx(0.0, **APPROX)
    assert m["composite_score"] is None
    assert m["composite_grade"] is None


def test_stdev_zero_ece_none():
    # all R equal -> sample stdev 0 -> ECE None
    rows = [
        Row(r_value=1.0, trade_datetime=_dt(1), win_loss="win"),
        Row(r_value=1.0, trade_datetime=_dt(2), win_loss="win"),
        Row(r_value=1.0, trade_datetime=_dt(3), win_loss="win"),
    ]
    m = compute_metrics(rows)
    assert m["ev"] == pytest.approx(1.0, **APPROX)
    assert m["ece"] is None
    assert m["composite_score"] is None


def test_span_zero_evol_none():
    # multiple trades, all on the same datetime -> span 0 -> evol None
    rows = [
        Row(r_value=2.0, trade_datetime=_dt(5), win_loss="win"),
        Row(r_value=-1.0, trade_datetime=_dt(5), win_loss="loss"),
    ]
    m = compute_metrics(rows)
    assert m["span_days"] == pytest.approx(0.0, **APPROX)
    assert m["evol"] is None
    assert m["composite_score"] is None


def test_dates_none_span_none():
    # no datetimes -> span None -> evol None; is/oos empty
    rows = [
        Row(r_value=2.0, trade_datetime=None, win_loss="win"),
        Row(r_value=-1.0, trade_datetime=None, win_loss="loss"),
    ]
    m = compute_metrics(rows)
    assert m["span_days"] is None
    assert m["first_trade_at"] is None
    assert m["last_trade_at"] is None
    assert m["evol"] is None
    assert m["composite_score"] is None
    is_t, oos_t = split_trades(rows, date(2024, 1, 1))
    assert is_t == []
    assert oos_t == []


def test_entry_none_not_counted_in_total():
    # entry None -> not in total_trades, but R still counts in R-stats
    rows = [
        Row(r_value=2.0, trade_datetime=_dt(1), win_loss="win", entry=100.0),
        Row(r_value=1.0, trade_datetime=_dt(2), win_loss="win", entry=None),
    ]
    m = compute_metrics(rows)
    assert m["total_trades"] == 1  # only the row with an entry
    assert m["ev"] == pytest.approx(1.5, **APPROX)  # both R values averaged
    assert m["total_r"] == pytest.approx(3.0, **APPROX)


def test_r_none_not_counted_in_r_stats():
    # r None -> excluded from EV/total_r/ece, but counts in total_trades
    rows = [
        Row(r_value=2.0, trade_datetime=_dt(1), win_loss="win"),
        Row(r_value=None, trade_datetime=_dt(2), win_loss=None),
        Row(r_value=-1.0, trade_datetime=_dt(3), win_loss="loss"),
    ]
    m = compute_metrics(rows)
    assert m["total_trades"] == 3
    assert m["ev"] == pytest.approx(0.5, **APPROX)  # mean of [2, -1]
    assert m["total_r"] == pytest.approx(1.0, **APPROX)


# --------------------------------------------------------------------------- #
# Phase-3 metrics: dedicated helper + edge-case tests
# --------------------------------------------------------------------------- #

def test_profit_factor_and_drawdown_example():
    # Task example: R = [1, -1, 2, -1, 3]
    #   gains = 6, losses = 2 -> PF = 3.0
    #   cumulative = [1, 0, 2, 1, 4] -> peaks [1,1,2,2,4] -> dd [0,1,0,1,0]
    #   max_dd = 1.0 ; total_r = 4.0 -> romad = 4.0
    rows = [
        Row(r_value=1.0, trade_datetime=_dt(1)),
        Row(r_value=-1.0, trade_datetime=_dt(2)),
        Row(r_value=2.0, trade_datetime=_dt(3)),
        Row(r_value=-1.0, trade_datetime=_dt(4)),
        Row(r_value=3.0, trade_datetime=_dt(5)),
    ]
    m = compute_metrics(rows)
    assert m["profit_factor"] == pytest.approx(3.0, **APPROX)
    assert m["max_drawdown_r"] == pytest.approx(1.0, **APPROX)
    assert m["romad"] == pytest.approx(4.0, **APPROX)


def test_profit_factor_none_without_losses():
    # only gains -> sum(R<0) == 0 -> PF None
    rows = [Row(r_value=1.0, trade_datetime=_dt(1)), Row(r_value=2.0, trade_datetime=_dt(2))]
    assert compute_metrics(rows)["profit_factor"] is None
    assert _profit_factor([1.0, 2.0]) is None
    assert _profit_factor([]) is None


def test_max_drawdown_from_peak_zero():
    # first trade negative -> curve [-1, -2, 0]; peak starts at 0 -> dd = 2.0
    rows = [
        Row(r_value=-1.0, trade_datetime=_dt(1)),
        Row(r_value=-1.0, trade_datetime=_dt(2)),
        Row(r_value=2.0, trade_datetime=_dt(3)),
    ]
    m = compute_metrics(rows)
    assert m["max_drawdown_r"] == pytest.approx(2.0, **APPROX)
    # total_r == 0 -> romad None guarded by max_dd, total_r here is 0.0
    assert m["total_r"] == pytest.approx(0.0, **APPROX)


def test_max_drawdown_sorts_unsorted_input():
    # Same R values as the example but shuffled -> must sort internally by date.
    ordered = [
        Row(r_value=1.0, trade_datetime=_dt(1)),
        Row(r_value=-1.0, trade_datetime=_dt(2)),
        Row(r_value=2.0, trade_datetime=_dt(3)),
        Row(r_value=-1.0, trade_datetime=_dt(4)),
        Row(r_value=3.0, trade_datetime=_dt(5)),
    ]
    shuffled = [ordered[3], ordered[0], ordered[4], ordered[1], ordered[2]]
    assert compute_metrics(shuffled)["max_drawdown_r"] == pytest.approx(1.0, **APPROX)


def test_max_drawdown_none_date_stable_last():
    # None-dated trade sorts stably to the end -> curve [1, -1, +5]
    #   cumulative [1, 0, 5] -> max_dd = 1.0 (the None trade appended last)
    rows = [
        Row(r_value=1.0, trade_datetime=_dt(1)),
        Row(r_value=-1.0, trade_datetime=_dt(2)),
        Row(r_value=5.0, trade_datetime=None),
    ]
    assert compute_metrics(rows)["max_drawdown_r"] == pytest.approx(1.0, **APPROX)


def test_romad_none_when_no_drawdown():
    # monotonically rising -> max_dd 0.0 -> romad None (guard against /0)
    rows = [
        Row(r_value=1.0, trade_datetime=_dt(1)),
        Row(r_value=2.0, trade_datetime=_dt(2)),
    ]
    m = compute_metrics(rows)
    assert m["max_drawdown_r"] == pytest.approx(0.0, **APPROX)
    assert m["romad"] is None


def test_skewness_none_below_three():
    assert _skewness([1.0, -1.0]) is None
    assert compute_metrics(
        [Row(r_value=1.0, trade_datetime=_dt(1)), Row(r_value=-1.0, trade_datetime=_dt(2))]
    )["skewness"] is None


def test_skewness_none_when_stdev_zero():
    assert _skewness([2.0, 2.0, 2.0]) is None


def test_skewness_excel_formula():
    # Excel SKEW([0,1,5]) = 1.5 * (18 / 7**1.5) = 1.4578629673213053
    assert _skewness([0.0, 1.0, 5.0]) == pytest.approx(1.4578629673213053, **APPROX)


def test_percentile_inc_interpolation():
    # sorted [0, 1, 2, 3, 4], n=5
    #   p50: rank 2.0 -> 2.0 (exact index, no interpolation)
    #   p25: rank 1.0 -> 1.0
    #   p10: rank 0.4 -> 0 + 0.4*(1-0) = 0.4
    data = [4.0, 0.0, 2.0, 1.0, 3.0]
    assert _percentile_inc(data, 0.5) == pytest.approx(2.0, **APPROX)
    assert _percentile_inc(data, 0.25) == pytest.approx(1.0, **APPROX)
    assert _percentile_inc(data, 0.10) == pytest.approx(0.4, **APPROX)
    assert _percentile_inc(data, 0.0) == pytest.approx(0.0, **APPROX)
    assert _percentile_inc(data, 1.0) == pytest.approx(4.0, **APPROX)


def test_percentile_inc_single_and_empty():
    assert _percentile_inc([7.0], 0.5) == 7.0
    assert _percentile_inc([7.0], 0.95) == 7.0
    assert _percentile_inc([], 0.5) is None


def test_empty_list_phase3_keys_present_and_none():
    m = compute_metrics([])
    for key in (
        "profit_factor", "max_drawdown_r", "romad", "skewness",
        "r_p05", "r_p25", "r_p50", "r_p75", "r_p95",
    ):
        assert key in m
        assert m[key] is None


# --------------------------------------------------------------------------- #
# Schema roundtrip: compute_metrics output validates + carries the new keys
# --------------------------------------------------------------------------- #

def test_metricsblock_schema_roundtrip():
    from app.schemas.metrics import MetricsBlock

    block = MetricsBlock.model_validate(compute_metrics(MAIN))
    dumped = block.model_dump()
    for key in (
        "profit_factor", "max_drawdown_r", "romad", "skewness",
        "r_p05", "r_p25", "r_p50", "r_p75", "r_p95",
    ):
        assert key in dumped
    assert dumped["profit_factor"] == pytest.approx(2.6, **APPROX)
    assert dumped["max_drawdown_r"] == pytest.approx(1.0, **APPROX)
    # Empty metrics validate too (all Phase-3 keys None but present).
    empty = MetricsBlock.model_validate(compute_metrics([])).model_dump()
    assert empty["profit_factor"] is None
    assert empty["r_p95"] is None


# --------------------------------------------------------------------------- #
# derive_win_loss
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "r,expected",
    [
        (0.5, "win"),
        (-0.05, None),   # -0.1 <= R < 0 -> blank
        (-0.1, None),    # boundary: not < -0.1
        (-0.11, "loss"),
        (0.0, "draw"),
        (None, None),
    ],
)
def test_derive_win_loss(r, expected):
    assert derive_win_loss(r) == expected


# --------------------------------------------------------------------------- #
# split_trades / compute_all
# --------------------------------------------------------------------------- #

def test_split_trades_boundary():
    split = date(2024, 1, 1)
    before = Row(r_value=1.0, trade_datetime=datetime(2023, 12, 31, 23, 59), win_loss="win")
    on = Row(r_value=1.0, trade_datetime=datetime(2024, 1, 1, 0, 0), win_loss="win")
    after = Row(r_value=1.0, trade_datetime=datetime(2024, 6, 1), win_loss="win")
    no_date = Row(r_value=1.0, trade_datetime=None, win_loss="win")
    is_t, oos_t = split_trades([before, on, after, no_date], split)
    assert is_t == [before]
    assert oos_t == [on, after]


def test_compute_all_shape():
    split = date(2024, 1, 1)
    rows = [
        Row(r_value=1.0, trade_datetime=datetime(2023, 6, 1), win_loss="win"),
        Row(r_value=-1.0, trade_datetime=datetime(2024, 6, 1), win_loss="loss"),
        Row(r_value=2.0, trade_datetime=None, win_loss="win"),
    ]
    result = compute_all(rows, split)
    assert set(result.keys()) == {"all", "is", "oos"}
    assert result["all"]["total_trades"] == 3
    assert result["is"]["total_trades"] == 1
    assert result["oos"]["total_trades"] == 1
