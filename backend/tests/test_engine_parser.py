"""Unit tests for the DB-free Hadrian_Engine parser (Phase 5, T3 / D2).

Logic is checked against tiny ``results.xlsx`` / ``backtest_N.xlsx`` workbooks
built with openpyxl in ``tmp_path``. A real-data smoke test runs only when the
``HADRIAN_ENGINE_RESULTS_DIR`` points at a real results directory.
"""

from __future__ import annotations

import os
from datetime import datetime

import openpyxl
import pytest

from app.importers.hadrian_engine import parse_hadrian_engine

from tests.paths import ENGINE_DIR

_REAL = ENGINE_DIR

_RESULTS_HEADER = [
    "Run#", "System", "Config Label", "TF", "Symbol", "Mode", "n", "WR%",
    "EV(R)", "Sharpe", "Calmar", "MaxDD(R)", "ProfitFactor", "R/yr",
    "Trades/yr", "Notes",
]
_TRADE_HEADER = [
    "#", "Date", "Entry Time", "Direction", "Entry$", "SL$", "Exit$",
    "Exit Time", "R_net", "W/L", "Duration", "Label",
]


def _write_results(path: str, rows: list[list]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(_RESULTS_HEADER)
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def _write_backtest(path: str, rules: tuple[str, str, str], trades: list[list]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Trades"
    ws.append(["Entry Rule:", rules[0]])
    ws.append(["Stop Loss Rule:", rules[1]])
    ws.append(["TP Rule:", rules[2]])
    ws.append([None])
    ws.append(_TRADE_HEADER)
    for t in trades:
        ws.append(t)
    wb.save(path)
    wb.close()


def _make_system(base: str, name: str, results_rows, backtests):
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    _write_results(os.path.join(d, "results.xlsx"), results_rows)
    for run, (rules, trades) in backtests.items():
        _write_backtest(os.path.join(d, f"backtest_{run}.xlsx"), rules, trades)
    return d


def _trade_row(n, date, entry_time, direction, entry, sl, exit_, r, wl):
    return [n, date, entry_time, direction, entry, sl, exit_, "", r, wl, "1 days", "lbl"]


# --------------------------------------------------------------------------- #
# Best-config selection
# --------------------------------------------------------------------------- #
def test_best_config_max_ev_over_full_negative(tmp_path):
    """A negative-EV 'full' run must NOT win
    over a higher-EV IS run (see docs/DECISIONS.md)."""
    base = str(tmp_path)
    _make_system(
        base,
        "dow_like",
        results_rows=[
            [1, "dow_like", "SwingSL", "1d", "BTC", "IS", 161, 20.5, 0.3749, 0, 0.49, 23.0, 1.43, 11.0, 30.0, None],
            [5, "dow_like", "ATRSL_BestTP", "1d", "BTC", "IS", 195, 14.9, 0.5815, 0, 1.22, 17.0, 1.66, 21.0, 36.0, None],
            [6, "dow_like", "ATRSL_BestTP", "1d", "BTC", "OOS", 128, 11.7, 0.2056, 0, 0.30, 26.0, 1.22, 7.9, 38.0, None],
            [8, "dow_like", "ProfileEngine", "1h", "BTC", "full", 1404, 11.0, -2.3529, 0, -0.43, 3325.0, 0.25, -1445.0, 614.0, None],
        ],
        backtests={
            5: (("swing", "atr", "candles"), [
                _trade_row(1, "2017-08-31", "2017-08-31 00:00", "long", 4724.89, 4586.24, 4586.24, -1.0235, "L"),
                _trade_row(2, "2017-09-04", "2017-09-04 10:30", "short", 4100.11, 4263.77, 4263.77, 2.5, "W"),
            ]),
        },
    )
    systems = parse_hadrian_engine(base)
    assert len(systems) == 1
    s = systems[0]
    assert s.name == "dow_like"
    assert s.parse_status == "complete"
    assert s.reported_metrics["run_number"] == 5
    assert s.reported_metrics["config_label"] == "ATRSL_BestTP"
    assert s.reported_metrics["total_trades"] == 195
    assert s.reported_metrics["ev"] == 0.5815
    assert s.reported_metrics["win_rate"] == pytest.approx(0.149)
    # is_ev / oos_ev pulled from companion rows of the same config
    assert s.reported_metrics["is_ev"] == 0.5815
    assert s.reported_metrics["oos_ev"] == 0.2056
    assert s.timeframe == "1d"
    assert len(s.trades) == 2


def test_full_preferred_as_tiebreak(tmp_path):
    """When a positive-EV 'full' run ties on EV with an IS run, 'full' wins."""
    base = str(tmp_path)
    _make_system(
        base,
        "tie_sys",
        results_rows=[
            [1, "tie_sys", "cfgA", "4h", "BTC", "IS", 100, 40.0, 0.30, 0, 1.0, 5.0, 1.5, 3.0, 20.0, None],
            [2, "tie_sys", "cfgB", "4h", "BTC", "full", 200, 42.0, 0.30, 0, 1.1, 4.0, 1.6, 4.0, 25.0, None],
        ],
        backtests={
            2: (("e", "s", "t"), [_trade_row(1, "2020-01-01", "2020-01-01 00:00", "long", 100, 90, 110, 1.0, "W")]),
        },
    )
    s = parse_hadrian_engine(base)[0]
    assert s.reported_metrics["run_number"] == 2
    assert s.reported_metrics["config_label"] == "cfgB"


def test_n_below_20_excluded(tmp_path):
    base = str(tmp_path)
    _make_system(
        base,
        "small_sys",
        results_rows=[
            [1, "small_sys", "cfgHi", "1d", "BTC", "IS", 14, 7.0, 2.46, 0, 0.48, 13.0, 3.5, 6.0, 2.0, "warn"],
            [2, "small_sys", "cfgOk", "1d", "BTC", "IS", 96, 10.0, 0.35, 0, 0.19, 33.0, 1.37, 6.0, 18.0, None],
        ],
        backtests={
            2: (("e", "s", "t"), [_trade_row(1, "2020-01-01", "2020-01-01 00:00", "long", 100, 90, 110, 0.35, "W")]),
        },
    )
    s = parse_hadrian_engine(base)[0]
    # n=14 row (EV 2.46) excluded -> best is the n=96 row
    assert s.reported_metrics["run_number"] == 2
    assert s.reported_metrics["total_trades"] == 96


def test_duplicate_rows_deduped(tmp_path):
    base = str(tmp_path)
    _make_system(
        base,
        "dup_sys",
        results_rows=[
            [1, "dup_sys", "cfg", "1d", "BTC", "IS", 50, 30.0, 0.40, 0, 1.0, 5.0, 1.5, 3.0, 20.0, None],
            [1, "dup_sys", "cfg", "1d", "BTC", "IS", 50, 30.0, 0.40, 0, 1.0, 5.0, 1.5, 3.0, 20.0, None],
        ],
        backtests={
            1: (("e", "s", "t"), [_trade_row(1, "2020-01-01", "2020-01-01 00:00", "long", 100, 90, 110, 0.4, "W")]),
        },
    )
    s = parse_hadrian_engine(base)[0]
    assert s.reported_metrics["run_number"] == 1


# --------------------------------------------------------------------------- #
# Trade mapping
# --------------------------------------------------------------------------- #
def test_trade_datetime_and_wl_mapping(tmp_path):
    base = str(tmp_path)
    _make_system(
        base,
        "tm_sys",
        results_rows=[
            [3, "tm_sys", "cfg", "1h", "BTC", "IS", 40, 30.0, 0.50, 0, 1.0, 5.0, 1.5, 3.0, 20.0, None],
        ],
        backtests={
            3: (("entry rule x", "sl rule y", "tp rule z"), [
                _trade_row(1, "2021-05-01", "2021-05-01 08:15", "long", 100, 95, 108, 1.6, "W"),
                _trade_row(2, "2021-05-02", "2021-05-02 09:00", "short", 200, 210, 210, -1.0, "L"),
                # W/L blank -> derive from R
                _trade_row(3, "2021-05-03", "2021-05-03 10:00", "long", 300, 290, 305, 0.5, ""),
                # only a date, no time -> midnight
                _trade_row(4, "2021-05-04", "2021-05-04", "short", 400, 410, 395, 0.4, "W"),
            ]),
        },
    )
    s = parse_hadrian_engine(base)[0]
    assert s.entry_rule == "entry rule x"
    assert s.sl_rule == "sl rule y"
    assert s.tp_rule == "tp rule z"
    t = s.trades
    assert t[0].trade_datetime == datetime(2021, 5, 1, 8, 15)
    assert t[0].direction == "long"
    assert t[0].entry == 100
    assert t[0].sl == 95
    assert t[0].exit == 108
    assert t[0].r_value == 1.6
    assert t[0].win_loss == "win"
    assert t[1].win_loss == "loss"
    assert t[2].win_loss == "win"  # derived from R>0
    assert t[3].trade_datetime == datetime(2021, 5, 4, 0, 0)
    assert t[3].timeframe == "1h"


def test_em_dash_rule_becomes_none(tmp_path):
    base = str(tmp_path)
    _make_system(
        base,
        "dash_sys",
        results_rows=[
            [1, "dash_sys", "cfg", "1d", "BTC", "IS", 30, 30.0, 0.30, 0, 1.0, 5.0, 1.5, 3.0, 20.0, None],
        ],
        backtests={
            1: (("—", "swing", "candles"), [_trade_row(1, "2020-01-01", "2020-01-01 00:00", "long", 100, 90, 110, 0.3, "W")]),
        },
    )
    s = parse_hadrian_engine(base)[0]
    assert s.entry_rule is None
    assert s.sl_rule == "swing"


# --------------------------------------------------------------------------- #
# Missing backtest / exclude list / missing dir
# --------------------------------------------------------------------------- #
def test_missing_backtest_is_reported_only(tmp_path):
    base = str(tmp_path)
    _make_system(
        base,
        "ro_sys",
        results_rows=[
            [7, "ro_sys", "cfg", "1d", "BTC", "IS", 40, 30.0, 0.30, 0, 1.0, 5.0, 1.5, 3.0, 20.0, None],
        ],
        backtests={},  # no backtest_7.xlsx
    )
    s = parse_hadrian_engine(base)[0]
    assert s.parse_status == "incomplete"
    assert s.trades == []
    assert "backtest_7.xlsx missing" in s.message
    assert s.reported_metrics["run_number"] == 7


def test_exclude_list(tmp_path):
    base = str(tmp_path)
    for name in ("engine_test", "minimal_test", "demo_sys_backup", "keep_me"):
        _make_system(
            base,
            name,
            results_rows=[[1, name, "cfg", "1d", "BTC", "IS", 40, 30.0, 0.30, 0, 1.0, 5.0, 1.5, 3.0, 20.0, None]],
            backtests={1: (("e", "s", "t"), [_trade_row(1, "2020-01-01", "2020-01-01 00:00", "long", 100, 90, 110, 0.3, "W")])},
        )
    systems = parse_hadrian_engine(base)
    assert [s.name for s in systems] == ["keep_me"]


def test_missing_directory_returns_empty_list():
    assert parse_hadrian_engine("/does/not/exist") == []
    assert parse_hadrian_engine("") == []


# --------------------------------------------------------------------------- #
# Real-data smoke test (auto-skip)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not os.path.isdir(_REAL), reason="real Hadrian_Engine results directory not present"
)
def test_real_data_smoke():
    systems = parse_hadrian_engine(_REAL)
    assert len(systems) == 19
    assert all(s.parse_status != "skipped" for s in systems)
    # best config = ATRSL_BestTP (Run#5, n=195) per the adjusted EV-max rule
    dow = next(s for s in systems if s.name == "brk_demo")
    assert dow.reported_metrics["config_label"] == "ATRSL_BestTP"
    assert dow.reported_metrics["run_number"] == 5
    assert len(dow.trades) == 195
    assert dow.reported_metrics["total_trades"] == 195
    assert dow.reported_metrics["ev"] == 0.5815
