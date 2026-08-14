"""Unit tests for the DB-free Hadrian² parser (Phase 5, T2 / D2 / D3).

Logic is checked against a small synthetic fixture under
``tests/fixtures/hadrian2_mini/``. A real-data smoke test runs only when the
``HADRIAN2_RESULTS_DIR`` points at a real results directory.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from app.importers.hadrian2 import parse_hadrian2

_MINI = os.path.join(os.path.dirname(__file__), "fixtures", "hadrian2_mini")
from tests.paths import HADRIAN2_DIR

_REAL = HADRIAN2_DIR


@pytest.fixture(scope="module")
def systems():
    return parse_hadrian2(_MINI)


def _by_name(systems):
    return {s.name: s for s in systems}


# --------------------------------------------------------------------------- #
# Naming table (D2)
# --------------------------------------------------------------------------- #
def test_naming_table_produces_all_13_systems(systems):
    names = {s.name for s in systems}
    assert names == {
        "MR-M15-101",
        "MR-M15-101.02",
        "MR-M15-101.03",
        "MR-M15-101.04",
        "MR-M15-101.05",
        "MR-M15-101.06",
        "MR-H1-101",
        "MR-H1-101.02",
        "MR-H1-101.03",
        "MR-H1-101.04",
        "MR-H4-101",
        "B-H1-101",
        "MR-H1-102",
    }


def test_timeframes_from_name(systems):
    s = _by_name(systems)
    assert s["MR-M15-101"].timeframe == "M15"
    assert s["MR-H1-101"].timeframe == "H1"
    assert s["MR-H4-101"].timeframe == "H4"
    assert s["B-H1-101"].timeframe == "H1"


# --------------------------------------------------------------------------- #
# Trade mapping (D2)
# --------------------------------------------------------------------------- #
def test_trade_mapping_from_audit_files(systems):
    base = _by_name(systems)["MR-M15-101"]
    assert base.parse_status == "complete"
    assert len(base.trades) == 3
    t0 = base.trades[0]
    assert t0.trade_datetime == datetime(2022, 1, 22, 9, 45, 0)
    assert t0.entry == 35142.09
    assert t0.sl == 34633.99
    assert t0.r_value == -1.044  # net_r
    assert t0.direction == "long"
    assert t0.win_loss == "loss"
    assert t0.timeframe == "M15"  # injected from the system, no column in file
    # derive_win_loss on the positive R trade
    assert base.trades[1].win_loss == "win"


def test_h1_base_has_its_own_trades(systems):
    base = _by_name(systems)["MR-H1-101"]
    assert len(base.trades) == 2
    assert base.trades[0].r_value == 2.0
    assert base.trades[0].timeframe == "H1"


def test_audited_variant_without_data_is_incomplete(systems):
    # Rank 2 has no master row / trade file in the mini fixture.
    s = _by_name(systems)["MR-M15-101.02"]
    assert s.parse_status == "incomplete"
    assert s.trades == []


# --------------------------------------------------------------------------- #
# Reported metrics (D2)
# --------------------------------------------------------------------------- #
def test_audited_reported_metrics(systems):
    m = _by_name(systems)["MR-M15-101"].reported_metrics
    assert m["total_trades"] == 216
    assert m["ev"] == 0.0952
    assert m["is_ev"] == 0.3066
    assert m["oos_ev"] == -0.0588
    assert m["verdict"] == "ARTIFACT"
    assert m["source_variant_id"].startswith("tf=15m")


def test_carrier_reported_metrics_pre_gate(systems):
    m = _by_name(systems)["B-H1-101"].reported_metrics
    assert m["pre_gate"] is True
    # best sufficient/confident variant = v4 (max oos_net_ev 0.25)
    assert m["oos_ev"] == 0.25
    assert m["ev"] == 0.12
    assert m["source_variant_id"] == "v4"


# --------------------------------------------------------------------------- #
# Sweep decomposition (D3)
# --------------------------------------------------------------------------- #
def test_system1_grid_categorical_axes(systems):
    s = _by_name(systems)["B-H1-101"]
    assert s.parse_status == "incomplete"
    assert len(s.sweeps) == 1
    g = s.sweeps[0]
    assert g.param_x == "tp_type"
    assert g.param_y == "sl_type"
    assert g.metric == "oos_net_ev"
    assert len(g.points) == 4
    # categorical values stay strings
    assert all(isinstance(p["x"], str) for p in g.points)


def test_system3_grid_numeric_axes_and_exact_values(systems):
    s = _by_name(systems)["MR-M15-101"]
    assert len(s.sweeps) == 1
    g = s.sweeps[0]
    assert g.param_x == "tp_norm"
    assert g.param_y == "sl_buffer"
    assert g.label == "trig=wick_any, el=-0.05, vf=0"
    assert len(g.points) == 4
    # numeric axes, ascending distinct
    xs = sorted({p["x"] for p in g.points})
    ys = sorted({p["y"] for p in g.points})
    assert xs == [0.25, 0.5]
    assert ys == [0.1, 0.2]
    assert all(isinstance(p["x"], float) for p in g.points)
    # exact value carried 1:1 from the CSV (t4: x=0.25, y=0.1 -> oos 0.30)
    cell = next(p for p in g.points if p["x"] == 0.25 and p["y"] == 0.1)
    assert cell["value"] == 0.30
    assert cell["net_ev"] == 0.17
    assert cell["n_trades"] == 540
    assert cell["low_confidence"] is False
    assert cell["insufficient_sample"] is False


def test_system3_grids_split_by_timeframe(systems):
    s = _by_name(systems)
    assert len(s["MR-M15-101"].sweeps) == 1  # 15m
    assert len(s["MR-H1-101"].sweeps) == 1   # 1h
    assert len(s["MR-H4-101"].sweeps) == 1   # 4h


def test_system2_grid(systems):
    g = _by_name(systems)["MR-H1-102"].sweeps
    assert len(g) == 1
    assert g[0].param_x == "tp_type"
    assert g[0].param_y == "sl_type"
    assert len(g[0].points) == 4


def test_total_sweep_points(systems):
    total = sum(len(g.points) for s in systems for g in s.sweeps)
    # 4 (sys1) + 4 (sys2) + 4 (s3 15m) + 2 (s3 1h) + 2 (s3 4h) = 16
    assert total == 16


# --------------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------------- #
def test_missing_directory_returns_empty_list():
    assert parse_hadrian2("/does/not/exist") == []
    assert parse_hadrian2("") == []


# --------------------------------------------------------------------------- #
# Real-data smoke test (auto-skip)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not os.path.isdir(_REAL), reason="real Hadrian² results directory not present"
)
def test_real_data_smoke():
    systems = parse_hadrian2(_REAL)
    assert len(systems) == 13
    assert sum(1 for s in systems if s.trades) == 10
    assert sum(len(s.trades) for s in systems) == 2151
    assert sum(len(s.sweeps) for s in systems) == 124
    assert sum(len(g.points) for s in systems for g in s.sweeps) == 2284
