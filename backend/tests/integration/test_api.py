"""Integration tests for the REST API.

Run against the dev_db Postgres server via the conftest fixtures. A FastAPI
``TestClient`` is wired to the per-test ``db_session`` through a
``dependency_override`` on ``get_db``. Auto-skipped when the server is missing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.models import System, Trade

pytestmark = pytest.mark.integration

# The exact MetricsBlock shape from the contract (18 base + 9 Phase-3 keys).
METRICS_KEYS = {
    "total_trades", "wins", "losses", "win_rate", "ev", "total_r",
    "avg_win_r", "avg_loss_r", "ece", "evol", "composite_score",
    "composite_grade", "ev_grade", "ece_grade", "evol_grade",
    "first_trade_at", "last_trade_at", "span_days",
    "profit_factor", "max_drawdown_r", "romad", "skewness",
    "r_p05", "r_p25", "r_p50", "r_p75", "r_p95",
}


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def seed(db_session):
    """Two systems: one complete with known trades, one incomplete w/o trades."""
    sys_a = System(
        name="B-H1-801",
        prefix="B",
        timeframe="H1",
        status="backtest",
        import_status="complete",
        entry_rule="break of prior high",
        sl_rule="below structure",
        tp_rule="2R fixed",
        notes=None,
        reported_metrics={"ev": 0.75, "total_trades": 4},
    )
    sys_b = System(
        name="MR-M15-802",
        prefix="MR",
        timeframe="M15",
        status="backtest",
        import_status="incomplete",
    )
    db_session.add_all([sys_a, sys_b])
    db_session.flush()

    trades = [
        # IS (before 2024-01-01): r = 2.0, -1.0
        Trade(system_id=sys_a.id, trade_datetime=datetime(2023, 6, 1, 12, 0),
              entry=100.0, sl=98.0, exit=104.0, direction="long",
              r_value=2.0, win_loss="win", source="manual"),
        Trade(system_id=sys_a.id, trade_datetime=datetime(2023, 7, 1, 12, 0),
              entry=100.0, sl=98.0, exit=98.0, direction="short",
              r_value=-1.0, win_loss="loss", source="manual"),
        # OOS (from 2024-01-01): r = 3.0, -1.0
        Trade(system_id=sys_a.id, trade_datetime=datetime(2024, 3, 1, 12, 0),
              entry=100.0, sl=98.0, exit=106.0, direction="long",
              r_value=3.0, win_loss="win", source="manual"),
        Trade(system_id=sys_a.id, trade_datetime=datetime(2024, 5, 1, 12, 0),
              entry=100.0, sl=98.0, exit=98.0, direction="short",
              r_value=-1.0, win_loss="loss", source="auto"),
    ]
    db_session.add_all(trades)
    db_session.commit()
    return {"sys_a": sys_a.id, "sys_b": sys_b.id}


def test_systems_list_shape_and_values(client, seed):
    r = client.get("/systems")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"split_date", "items"}
    assert body["split_date"] == "2024-01-01"

    # ordered by name -> B-H1-801 first
    item = body["items"][0]
    assert set(item.keys()) == {
        "id", "name", "prefix", "timeframe", "asset", "status", "import_status",
        "provenance", "source_engine", "origin", "metrics",
    }
    assert item["name"] == "B-H1-801"
    assert item["prefix"] == "B"
    assert item["import_status"] == "complete"
    # Pre-existing systems default to manual with no source engine.
    assert item["provenance"] == "manual"
    assert item["source_engine"] is None
    # Systems seeded straight into the DB carry the default origin='import'.
    assert item["origin"] == "import"

    metrics = item["metrics"]
    assert set(metrics.keys()) == {"all", "is", "oos"}
    for block in metrics.values():
        assert set(block.keys()) == METRICS_KEYS

    assert metrics["all"]["total_trades"] == 4
    assert metrics["all"]["ev"] == pytest.approx(0.75)
    # Phase-3 keys present with values: R=[2,-1,3,-1] -> PF = 5/2 = 2.5
    assert metrics["all"]["profit_factor"] == pytest.approx(2.5)
    assert metrics["all"]["max_drawdown_r"] == pytest.approx(1.0)
    assert metrics["all"]["r_p50"] is not None
    assert metrics["is"]["total_trades"] == 2
    assert metrics["is"]["ev"] == pytest.approx(0.5)
    assert metrics["oos"]["total_trades"] == 2
    assert metrics["oos"]["ev"] == pytest.approx(1.0)

    # incomplete system with no trades
    sys_b = next(i for i in body["items"] if i["name"] == "MR-M15-802")
    assert sys_b["import_status"] == "incomplete"
    assert sys_b["metrics"]["all"]["total_trades"] == 0
    assert sys_b["metrics"]["all"]["ev"] is None


def test_systems_provenance_filter(client, seed):
    # Both seeded systems are manual, so ?provenance=manual returns all.
    all_items = client.get("/systems").json()["items"]
    manual = client.get("/systems", params={"provenance": "manual"}).json()["items"]
    assert {i["name"] for i in manual} == {i["name"] for i in all_items}
    assert all(i["provenance"] == "manual" for i in manual)

    # No programmatic systems in the seed -> empty.
    prog = client.get("/systems", params={"provenance": "programmatic"}).json()
    assert prog["items"] == []

    # Invalid value -> 422.
    assert client.get("/systems", params={"provenance": "bogus"}).status_code == 422


def test_systems_provenance_filter_programmatic(client, db_session):
    prog_sys = System(
        name="MR-M15-101",
        prefix="MR",
        timeframe="M15",
        status="backtest",
        import_status="complete",
        provenance="programmatic",
        source_engine="hadrian2",
    )
    db_session.add(prog_sys)
    db_session.commit()

    prog = client.get("/systems", params={"provenance": "programmatic"}).json()["items"]
    assert [i["name"] for i in prog] == ["MR-M15-101"]
    assert prog[0]["provenance"] == "programmatic"
    assert prog[0]["source_engine"] == "hadrian2"

    manual = client.get("/systems", params={"provenance": "manual"}).json()["items"]
    assert "MR-M15-101" not in {i["name"] for i in manual}


def test_system_detail_has_provenance(client, seed):
    body = client.get(f"/systems/{seed['sys_a']}").json()
    assert body["provenance"] == "manual"
    assert body["source_engine"] is None


def test_system_detail(client, seed):
    r = client.get(f"/systems/{seed['sys_a']}")
    assert r.status_code == 200
    body = r.json()
    for key in ("entry_rule", "sl_rule", "tp_rule", "notes", "reported_metrics"):
        assert key in body
    assert body["entry_rule"] == "break of prior high"
    assert body["notes"] is None
    assert body["reported_metrics"] == {"ev": 0.75, "total_trades": 4}
    assert set(body["metrics"].keys()) == {"all", "is", "oos"}
    # Phase-3 additive: split_date + Phase-3 metric key in the detail response.
    assert body["split_date"] == "2024-01-01"
    assert body["metrics"]["all"]["profit_factor"] == pytest.approx(2.5)


def test_system_detail_404(client, seed):
    assert client.get("/systems/99999").status_code == 404


def test_trades_filters(client, seed):
    sid = seed["sys_a"]

    r = client.get("/trades", params={"system_id": sid})
    body = r.json()
    assert r.status_code == 200
    assert set(body.keys()) == {"total", "limit", "offset", "items"}
    assert body["total"] == 4
    assert len(body["items"]) == 4
    first = body["items"][0]
    assert first["system_name"] == "B-H1-801"

    # direction filter
    body = client.get("/trades", params={"system_id": sid, "direction": "long"}).json()
    assert body["total"] == 2
    assert all(t["direction"] == "long" for t in body["items"])

    # win_loss filter
    body = client.get("/trades", params={"system_id": sid, "win_loss": "win"}).json()
    assert body["total"] == 2

    # source filter
    assert client.get("/trades", params={"source": "auto"}).json()["total"] == 1
    assert client.get("/trades", params={"source": "manual"}).json()["total"] == 3

    # date_from inclusive
    body = client.get("/trades", params={"date_from": "2024-01-01"}).json()
    assert body["total"] == 2

    # date_to inclusive (end of day) -> everything before 2024-01-01
    body = client.get("/trades", params={"date_to": "2023-12-31"}).json()
    assert body["total"] == 2


def test_trades_pagination_and_order(client, seed):
    p0 = client.get("/trades", params={"limit": 2, "offset": 0}).json()
    p1 = client.get("/trades", params={"limit": 2, "offset": 2}).json()
    assert p0["total"] == p1["total"] == 4
    assert len(p0["items"]) == 2
    assert len(p1["items"]) == 2
    assert {t["id"] for t in p0["items"]}.isdisjoint({t["id"] for t in p1["items"]})

    asc = client.get("/trades", params={"order": "asc"}).json()["items"]
    desc = client.get("/trades", params={"order": "desc"}).json()["items"]
    assert asc[0]["trade_datetime"] == "2023-06-01T12:00:00"
    assert desc[0]["trade_datetime"] == "2024-05-01T12:00:00"


def test_trades_limit_validation(client, seed):
    assert client.get("/trades", params={"limit": 0}).status_code == 422
    assert client.get("/trades", params={"limit": 10001}).status_code == 422


def test_patch_system_status(client, seed):
    r = client.patch(f"/systems/{seed['sys_a']}", json={"status": "live_testing"})
    assert r.status_code == 200
    assert r.json()["status"] == "live_testing"

    # invalid value -> 422
    bad = client.patch(f"/systems/{seed['sys_a']}", json={"status": "bogus"})
    assert bad.status_code == 422


def test_patch_system_rules_notes_timeframe_tracks_overrides(client, seed):
    sid = seed["sys_a"]
    r = client.patch(
        f"/systems/{sid}",
        json={"entry_rule": "new entry", "notes": "note text"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["entry_rule"] == "new entry"
    assert body["notes"] == "note text"
    assert set(body["user_overrides"]) == {"entry_rule", "notes"}

    # A follow-up patch grows the override list (dedup, no in-place mutation).
    r2 = client.patch(f"/systems/{sid}", json={"tp_rule": "3R", "timeframe": "H4"})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["tp_rule"] == "3R"
    assert body2["timeframe"] == "H4"
    assert set(body2["user_overrides"]) == {
        "entry_rule", "notes", "tp_rule", "timeframe"
    }
    # Re-patching the same field does not duplicate it.
    r3 = client.patch(f"/systems/{sid}", json={"entry_rule": "again"})
    overrides = r3.json()["user_overrides"]
    assert len(overrides) == len(set(overrides))


def test_patch_system_empty_body_is_noop(client, seed):
    sid = seed["sys_a"]
    r = client.patch(f"/systems/{sid}", json={})
    assert r.status_code == 200
    assert r.json()["user_overrides"] == []
    assert r.json()["status"] == "backtest"


def test_patch_system_404(client, seed):
    assert client.patch("/systems/99999", json={"notes": "x"}).status_code == 404


def test_delete_system_cascades(client, seed, db_session):
    from sqlalchemy import func, select

    from app.models import Concept, ParameterSweep, SystemConcept, Trade

    sid = seed["sys_a"]

    # Attach a parameter sweep and a concept link so the cascade is observable.
    concept = Concept(name="Delete-Test-Concept")
    db_session.add(concept)
    db_session.flush()
    db_session.add(ParameterSweep(system_id=sid, points=[]))
    db_session.add(SystemConcept(system_id=sid, concept_id=concept.id, source="manual"))
    db_session.commit()

    assert db_session.execute(
        select(func.count(Trade.id)).where(Trade.system_id == sid)
    ).scalar_one() == 4
    assert db_session.execute(
        select(func.count(ParameterSweep.id)).where(ParameterSweep.system_id == sid)
    ).scalar_one() == 1
    assert db_session.execute(
        select(func.count(SystemConcept.id)).where(SystemConcept.system_id == sid)
    ).scalar_one() == 1

    r = client.delete(f"/systems/{sid}")
    assert r.status_code == 204

    assert db_session.execute(
        select(func.count(Trade.id)).where(Trade.system_id == sid)
    ).scalar_one() == 0
    assert db_session.execute(
        select(func.count(ParameterSweep.id)).where(ParameterSweep.system_id == sid)
    ).scalar_one() == 0
    assert db_session.execute(
        select(func.count(SystemConcept.id)).where(SystemConcept.system_id == sid)
    ).scalar_one() == 0

    # The concept itself survives (only the link cascades).
    assert db_session.get(Concept, concept.id) is not None

    # Second delete / get -> 404.
    assert client.delete(f"/systems/{sid}").status_code == 404
    assert client.get(f"/systems/{sid}").status_code == 404


def test_import_missing_file_404(client):
    r = client.post("/import/xlsx", json={"path": "/nope.xlsx"})
    assert r.status_code == 404


def test_import_configured_xlsx(client):
    """POST /import/xlsx with no body imports whatever ``XLSX_PATH`` points at.

    Asserted against the file rather than against fixed counts, so this passes
    with the shipped sample and with a private workbook alike.
    """
    if not Path(settings.XLSX_PATH).is_file():
        pytest.skip(f"no workbook at {settings.XLSX_PATH}")

    expected_tabs = len(
        openpyxl.load_workbook(settings.XLSX_PATH, read_only=True).sheetnames
    )

    r = client.post("/import/xlsx")
    assert r.status_code == 200
    body = r.json()
    assert body["tabs_total"] == expected_tabs
    assert len(body["tab_results"]) == expected_tabs
    assert body["trades_imported"] > 0


def test_openapi(client):
    assert client.get("/openapi.json").status_code == 200
