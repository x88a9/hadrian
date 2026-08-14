"""Integration tests for the quant-analytics API (Phase 5, T6/D5).

Run against the dev_db Postgres server via the conftest fixtures with a
FastAPI ``TestClient`` wired to the per-test ``db_session``. Data is seeded
synthetically (no real source files needed).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import ParameterSweep, System, Trade

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _point(x, y, value, net_ev=0.0, n_trades=100, low=False, insuff=False):
    return {
        "x": x, "y": y, "value": value, "net_ev": net_ev, "n_trades": n_trades,
        "low_confidence": low, "insufficient_sample": insuff,
    }


@pytest.fixture()
def seed(db_session):
    """A system carrying one numeric 2x3 sweep grid, one bare system without
    sweeps, a system with dense monthly dated trades (walk-forward), and one
    with varied R values (Monte-Carlo)."""
    sys_topo = System(name="MR-M15-101", prefix="MR", timeframe="M15",
                       status="backtest", import_status="incomplete",
                       provenance="programmatic", source_engine="hadrian2")
    sys_bare = System(name="MR-H1-102", prefix="MR", timeframe="H1",
                      status="backtest", import_status="incomplete",
                      provenance="programmatic", source_engine="hadrian2")
    sys_wf = System(name="MR-M15-201", prefix="MR", timeframe="M15",
                    status="backtest", import_status="complete")
    sys_mc = System(name="MR-M15-202", prefix="MR", timeframe="M15",
                    status="backtest", import_status="complete")
    db_session.add_all([sys_topo, sys_bare, sys_wf, sys_mc])
    db_session.flush()

    # Deliberately scrambled input order; x/y are numeric so axes must come out
    # ascending. x in {0.5, 0.25, 0.75}, y in {0.2, 0.1}.
    points = [
        _point(0.75, 0.2, -0.05),
        _point(0.25, 0.1, 0.27),
        _point(0.5, 0.2, 0.10),
        _point(0.25, 0.2, 0.05),
        _point(0.75, 0.1, 0.30),
        _point(0.5, 0.1, 0.21),
    ]
    db_session.add(ParameterSweep(
        system_id=sys_topo.id, label="trig=wick_any, el=-0.05, vf=0",
        param_x="tp_norm", param_y="sl_buffer", metric="oos_net_ev",
        points=points,
    ))

    # 24 monthly dated trades, all r=1.0 -> every evaluated OOS window is
    # positive -> pct_positive should be exactly 100.0 (proves percent scaling).
    wf_trades = []
    for i in range(24):
        year = 2023 + i // 12
        month = i % 12 + 1
        wf_trades.append(Trade(
            system_id=sys_wf.id, trade_datetime=datetime(year, month, 15, 12, 0),
            entry=100.0, sl=99.0, exit=101.0, direction="long",
            r_value=1.0, win_loss="win", source="auto",
        ))
    db_session.add_all(wf_trades)

    # Varied R values (with an undated / null-R noise trade) for Monte-Carlo.
    mc_r = [2.0, -1.0, 1.5, -1.0, 3.0, -1.0, 0.5, -1.0, 2.5, -1.0,
            1.0, -1.0, 2.0, -1.0, 1.2, -1.0, 0.8, -1.0, 1.7, -1.0]
    mc_trades = [
        Trade(system_id=sys_mc.id, trade_datetime=datetime(2024, 1, 1, 12, 0),
              entry=100.0, sl=99.0, exit=101.0, direction="long",
              r_value=r, win_loss="win" if r > 0 else "loss", source="auto")
        for r in mc_r
    ]
    # a noise trade without an R value (must be excluded from n_trades)
    mc_trades.append(Trade(system_id=sys_mc.id, trade_datetime=None,
                           entry=100.0, sl=99.0, exit=100.0, direction="long",
                           r_value=None, win_loss=None, source="auto"))
    db_session.add_all(mc_trades)

    db_session.commit()
    return {"topo": sys_topo.id, "bare": sys_bare.id,
            "wf": sys_wf.id, "mc": sys_mc.id}


# --------------------------------------------------------------------------- #
# Topography
# --------------------------------------------------------------------------- #

def test_topography_shape(client, seed):
    r = client.get(f"/systems/{seed['topo']}/topography")
    assert r.status_code == 200
    body = r.json()
    assert body["system_id"] == seed["topo"]
    assert body["pre_gate"] is True
    assert len(body["grids"]) == 1

    grid = body["grids"][0]
    assert grid["label"] == "trig=wick_any, el=-0.05, vf=0"
    assert grid["param_x"] == "tp_norm"
    assert grid["param_y"] == "sl_buffer"
    assert grid["metric"] == "oos_net_ev"
    # numeric axes ascending regardless of input order
    assert grid["x_values"] == [0.25, 0.5, 0.75]
    assert grid["y_values"] == [0.1, 0.2]
    assert len(grid["cells"]) == 6

    # every cell carries the full neighbour block
    for cell in grid["cells"]:
        for key in ("neighbor_min", "neighbor_max", "neighbor_mean",
                    "n_neighbors", "value", "net_ev", "n_trades"):
            assert key in cell

    # interior-ish cell (0.5, 0.1) sits mid-grid -> has all 5 neighbours here
    mid = next(c for c in grid["cells"] if c["x"] == 0.5 and c["y"] == 0.1)
    assert mid["n_neighbors"] == 5
    assert mid["neighbor_min"] is not None

    # a corner cell has fewer neighbours than the mid cell
    corner = next(c for c in grid["cells"] if c["x"] == 0.25 and c["y"] == 0.1)
    assert corner["n_neighbors"] < mid["n_neighbors"]

    assert grid["pct_positive"] == pytest.approx(5 / 6)  # fraction, not percent
    assert grid["best"]["value"] == pytest.approx(0.30)
    assert "floor" in grid["robust_best"]


def test_topography_no_sweeps(client, seed):
    r = client.get(f"/systems/{seed['bare']}/topography")
    assert r.status_code == 200
    assert r.json()["grids"] == []


def test_topography_404(client, seed):
    assert client.get("/systems/999999/topography").status_code == 404


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #

def test_walkforward_default(client, seed):
    r = client.get(f"/systems/{seed['wf']}/walkforward")
    assert r.status_code == 200
    body = r.json()
    assert body["system_id"] == seed["wf"]
    assert body["is_months"] == 6
    assert body["oos_months"] == 3
    assert body["step_months"] == 3
    assert body["n_dated_trades"] == 24
    assert body["n_windows"] >= 1
    # all R positive -> every evaluated window positive -> 100 percent (not 1.0)
    assert body["pct_positive"] == pytest.approx(100.0)
    win = body["windows"][0]
    assert set(win.keys()) == {
        "index", "is_start", "is_end", "oos_start", "oos_end",
        "n_is", "n_oos", "is_ev", "oos_ev",
    }


def test_walkforward_smaller_windows_change_count(client, seed):
    default = client.get(f"/systems/{seed['wf']}/walkforward").json()
    small = client.get(
        f"/systems/{seed['wf']}/walkforward",
        params={"is_months": 3, "oos_months": 1},
    ).json()
    assert small["is_months"] == 3
    assert small["oos_months"] == 1
    assert small["step_months"] == 1
    # narrower windows + smaller step -> strictly more windows
    assert small["n_windows"] > default["n_windows"]


def test_walkforward_validation(client, seed):
    assert client.get(
        f"/systems/{seed['wf']}/walkforward", params={"is_months": 0}
    ).status_code == 422
    assert client.get(
        f"/systems/{seed['wf']}/walkforward", params={"oos_months": 0}
    ).status_code == 422


def test_walkforward_404(client, seed):
    assert client.get("/systems/999999/walkforward").status_code == 404


# --------------------------------------------------------------------------- #
# Monte-Carlo
# --------------------------------------------------------------------------- #

def test_montecarlo_deterministic_seed(client, seed):
    a = client.get(f"/systems/{seed['mc']}/montecarlo", params={"seed": 7}).json()
    b = client.get(f"/systems/{seed['mc']}/montecarlo", params={"seed": 7}).json()
    assert a == b
    assert a["n_trades"] == 20  # the null-R noise trade is excluded
    assert a["n_iterations"] == 1000
    assert a["horizon"] == 20
    assert a["ev_p50"] is not None
    assert len(a["ev_histogram"]) == 30
    assert set(a["equity_fan"].keys()) == {"steps", "p5", "p25", "p50", "p75", "p95"}


def test_montecarlo_different_seed_differs(client, seed):
    a = client.get(f"/systems/{seed['mc']}/montecarlo", params={"seed": 1}).json()
    b = client.get(f"/systems/{seed['mc']}/montecarlo", params={"seed": 2}).json()
    assert a != b


def test_montecarlo_n_cap(client, seed):
    assert client.get(
        f"/systems/{seed['mc']}/montecarlo", params={"n": 20000}
    ).status_code == 422
    assert client.get(
        f"/systems/{seed['mc']}/montecarlo", params={"n": 0}
    ).status_code == 422


def test_montecarlo_no_r_trades(client, seed):
    body = client.get(f"/systems/{seed['bare']}/montecarlo").json()
    assert body["n_trades"] == 0
    assert body["ev_p50"] is None
    assert body["p_ev_positive"] is None
    assert body["ev_histogram"] == []
    assert body["equity_fan"]["steps"] == []
    assert body["equity_fan"]["p5"] == []


def test_montecarlo_404(client, seed):
    assert client.get("/systems/999999/montecarlo").status_code == 404


# --------------------------------------------------------------------------- #
# Regression
# --------------------------------------------------------------------------- #

def test_openapi_has_quant_paths(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/systems/{system_id}/topography" in paths
    assert "/systems/{system_id}/walkforward" in paths
    assert "/systems/{system_id}/montecarlo" in paths
