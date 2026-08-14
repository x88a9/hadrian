"""Integration tests for the Phase 2 ingest endpoints (T1 POST /systems,
T2 POST /trades). Run against the dev_db Postgres server; auto-skipped when the
server is missing (see conftest)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# T1 - POST /systems
# --------------------------------------------------------------------------- #
def test_post_system_creates_with_derived_fields(client):
    r = client.post(
        "/systems",
        json={"name": "EMA-M1-900.demo", "entry_rule": "ema cross"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "EMA-M1-900.demo"
    assert body["prefix"] == "EMA"
    assert body["timeframe"] == "M1"
    assert body["import_status"] == "complete"
    assert body["status"] == "backtest"  # server default
    assert body["entry_rule"] == "ema cross"
    assert body["sl_rule"] is None
    # SystemDetail shape
    assert set(body["metrics"].keys()) == {"all", "is", "oos"}


def test_post_system_idempotent_partial_update(client):
    first = client.post("/systems", json={"name": "B-H1-050", "entry_rule": "e1"})
    assert first.status_code == 201

    # Second POST with the same name -> 200, partial update (only tp_rule).
    second = client.post(
        "/systems", json={"name": "B-H1-050", "tp_rule": "2R"}
    )
    assert second.status_code == 200
    body = second.json()
    assert body["entry_rule"] == "e1"  # untouched
    assert body["tp_rule"] == "2R"  # updated
    assert body["id"] == first.json()["id"]  # no duplicate

    # Only one system with that name exists.
    systems = client.get("/systems").json()["items"]
    assert sum(1 for s in systems if s["name"] == "B-H1-050") == 1


def test_post_system_invalid_status_422(client):
    r = client.post("/systems", json={"name": "B-H1-051", "status": "bogus"})
    assert r.status_code == 422


def test_post_system_appears_in_list(client):
    client.post("/systems", json={"name": "MR-M15-777"})
    names = [s["name"] for s in client.get("/systems").json()["items"]]
    assert "MR-M15-777" in names


# --------------------------------------------------------------------------- #
# T2 - POST /trades
# --------------------------------------------------------------------------- #
def _make_system(client, name="B-H1-060"):
    return client.post("/systems", json={"name": name}).json()["id"]


def test_post_trade_by_system_name_auto_and_derived_win_loss(client):
    _make_system(client, "B-H1-060")
    r = client.post(
        "/trades",
        json={
            "system_name": "B-H1-060",
            "trade_datetime": "2024-03-01T12:00:00",
            "direction": "long",
            "entry": 100.0,
            "sl": 98.0,
            "exit": 104.0,
            "r_value": 2.0,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "auto"
    assert body["win_loss"] == "win"  # derived from r_value
    assert body["system_name"] == "B-H1-060"

    # Shows up in the auto-filtered trade list.
    auto = client.get("/trades", params={"source": "auto"}).json()
    assert auto["total"] == 1
    assert auto["items"][0]["id"] == body["id"]


def test_post_trade_reflected_in_system_metrics(client):
    sid = _make_system(client, "B-H1-061")
    client.post(
        "/trades",
        json={"system_id": sid, "trade_datetime": "2024-03-01T12:00:00",
              "r_value": 2.0, "entry": 100.0},
    )
    detail = client.get(f"/systems/{sid}").json()
    assert detail["metrics"]["all"]["total_trades"] == 1
    assert detail["metrics"]["all"]["ev"] == pytest.approx(2.0)


def test_post_trade_unknown_system_404(client):
    by_id = client.post("/trades", json={"system_id": 999999, "r_value": 1.0})
    assert by_id.status_code == 404
    by_name = client.post("/trades", json={"system_name": "does-not-exist", "r_value": 1.0})
    assert by_name.status_code == 404


def test_post_trade_neither_or_both_refs_422(client):
    _make_system(client, "B-H1-062")
    neither = client.post("/trades", json={"r_value": 1.0})
    assert neither.status_code == 422
    both = client.post(
        "/trades", json={"system_id": 1, "system_name": "B-H1-062", "r_value": 1.0}
    )
    assert both.status_code == 422
