"""Integration tests for GET /systems/{id}/report (T5)."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import Concept, System, SystemConcept, Trade

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_report_summary_handverified(client, db_session):
    system = System(
        name="B-H1-100",
        prefix="B",
        timeframe="H1",
        status="active",
        import_status="complete",
        entry_rule="break of high",
    )
    system.trades = [
        Trade(
            trade_datetime=datetime(2025, 1, 10, 9, 0),
            direction="long",
            r_value=2.5,
            win_loss="win",
            source="manual",
        ),
        Trade(
            trade_datetime=datetime(2025, 3, 15, 14, 0),
            direction="short",
            r_value=-1.0,
            win_loss="loss",
            source="manual",
        ),
        Trade(
            trade_datetime=datetime(2025, 2, 1, 10, 0),
            direction="long",
            r_value=1.0,
            win_loss="win",
            source="manual",
        ),
        # undated
        Trade(direction="short", r_value=-0.5, win_loss="draw", source="manual"),
    ]
    concept = Concept(name="Liquidity")
    db_session.add_all([system, concept])
    db_session.flush()
    db_session.add(SystemConcept(system_id=system.id, concept_id=concept.id))
    db_session.commit()

    r = client.get(f"/systems/{system.id}/report")
    assert r.status_code == 200
    body = r.json()

    assert body["report_version"] == 1
    assert body["generated_at"] is not None
    assert body["system"]["name"] == "B-H1-100"
    assert body["system"]["entry_rule"] == "break of high"

    assert [c["name"] for c in body["concepts"]] == ["Liquidity"]

    s = body["trades_summary"]
    assert s["total"] == 4
    assert s["long_count"] == 2
    assert s["short_count"] == 2
    assert s["best_r"] == 2.5
    assert s["worst_r"] == -1.0
    assert s["undated_count"] == 1
    assert s["first_trade_at"].startswith("2025-01-10")
    assert s["last_trade_at"].startswith("2025-03-15")


def test_report_system_without_trades(client, db_session):
    system = System(
        name="MR-M15-200",
        prefix="MR",
        timeframe="M15",
        status="backtest",
        import_status="incomplete",
    )
    db_session.add(system)
    db_session.commit()

    body = client.get(f"/systems/{system.id}/report").json()
    s = body["trades_summary"]
    assert s["total"] == 0
    assert s["long_count"] == 0
    assert s["short_count"] == 0
    assert s["best_r"] is None
    assert s["worst_r"] is None
    assert s["first_trade_at"] is None
    assert s["last_trade_at"] is None
    assert s["undated_count"] == 0
    assert body["concepts"] == []


def test_report_unknown_system_404(client):
    assert client.get("/systems/99999/report").status_code == 404
