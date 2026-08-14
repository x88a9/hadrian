"""Integration tests for POST /import/csv (Phase 2, T3 / D2, D3, D5).

Run against the dev_db Postgres server; auto-skipped when the server is missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.models import System, Trade
from app.services.import_service import run_xlsx_import

pytestmark = pytest.mark.integration

CSV = (
    "entry_time,exit_time,direction,entry_price,sl_price,exit_price,"
    "tp_price,exit_reason,gross_r,net_r,timeframe\n"
    "2024-03-01 12:00:00,2024-03-01 13:00:00,long,100.0,98.0,104.0,110.0,tp,3.0,2.0,M15\n"
    "2024-03-02 09:00:00,2024-03-02 10:00:00,short,100.0,102.0,98.0,90.0,tp,2.5,1.0,M15\n"
    "notadate,,notanumber,,,,,,,,\n"  # broken row -> skipped
).encode("utf-8")


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _upload(client, name, data=CSV, replace="true"):
    return client.post(
        "/import/csv",
        files={"file": ("trades.csv", data, "text/csv")},
        data={"system_name": name, "replace": replace},
    )


def _count(db, system_id, source):
    return db.execute(
        select(func.count())
        .select_from(Trade)
        .where(Trade.system_id == system_id, Trade.source == source)
    ).scalar_one()


def test_csv_upload_creates_auto_trades(client, db_session):
    r = _upload(client, "EMA-M1-900.demo")
    assert r.status_code == 200
    body = r.json()
    assert body["tabs_total"] == 1
    assert body["trades_imported"] == 2  # 2 valid, 1 skipped
    assert body["file_path"] == "trades.csv"
    assert len(body["tab_results"]) == 1
    tr = body["tab_results"][0]
    assert tr["system_name"] == "EMA-M1-900.demo"
    assert tr["trades"] == 2
    assert "1 rows skipped" in tr["message"]

    # System created (D3) with derived fields.
    system = db_session.execute(
        select(System).where(System.name == "EMA-M1-900.demo")
    ).scalar_one()
    assert system.prefix == "EMA"
    assert system.timeframe == "M1"

    # Trades persisted as source='auto'.
    assert _count(db_session, system.id, "auto") == 2
    autos = db_session.execute(
        select(Trade).where(Trade.system_id == system.id)
    ).scalars().all()
    assert all(t.source == "auto" for t in autos)
    assert {t.win_loss for t in autos} == {"win"}  # r 2.0 and 1.0


def test_csv_reupload_is_idempotent(client, db_session):
    _upload(client, "EMA-M1-901")
    system = db_session.execute(
        select(System).where(System.name == "EMA-M1-901")
    ).scalar_one()
    assert _count(db_session, system.id, "auto") == 2

    # Re-upload with replace=true -> same counts (full mirror, D2).
    r = _upload(client, "EMA-M1-901")
    assert r.status_code == 200
    assert _count(db_session, system.id, "auto") == 2


def test_csv_replace_false_appends(client, db_session):
    _upload(client, "EMA-M1-902", replace="true")
    system = db_session.execute(
        select(System).where(System.name == "EMA-M1-902")
    ).scalar_one()
    assert _count(db_session, system.id, "auto") == 2

    _upload(client, "EMA-M1-902", replace="false")
    assert _count(db_session, system.id, "auto") == 4


def test_manual_trades_survive_csv_replace(client, db_session):
    _upload(client, "EMA-M1-903")
    system = db_session.execute(
        select(System).where(System.name == "EMA-M1-903")
    ).scalar_one()

    db_session.add(
        Trade(system_id=system.id, r_value=1.5, entry=100.0,
              win_loss="win", source="manual")
    )
    db_session.commit()
    assert _count(db_session, system.id, "manual") == 1

    # replace=true wipes only auto trades.
    _upload(client, "EMA-M1-903", replace="true")
    assert _count(db_session, system.id, "auto") == 2
    assert _count(db_session, system.id, "manual") == 1


def test_csv_without_known_columns_400(client):
    bad = "foo,bar\n1,2\n".encode("utf-8")
    r = _upload(client, "EMA-M1-904", data=bad)
    assert r.status_code == 400


def test_xlsx_reimport_keeps_auto_trades(client, db_session):
    if not Path(settings.XLSX_PATH).is_file():
        pytest.skip(f"canonical xlsx missing at {settings.XLSX_PATH}")

    run_xlsx_import(db_session, settings.XLSX_PATH)
    system = db_session.execute(
        select(System)
        .where(System.import_status == "complete")
        .order_by(System.name)
    ).scalars().first()
    assert system is not None
    manual_before = _count(db_session, system.id, "manual")
    assert manual_before > 0

    # Attach auto trades to that existing system via CSV.
    _upload(client, system.name)
    auto_count = _count(db_session, system.id, "auto")
    assert auto_count == 2

    # Re-run the xlsx import: manual trades are replaced, auto trades survive.
    run_xlsx_import(db_session, settings.XLSX_PATH)
    assert _count(db_session, system.id, "auto") == auto_count
    assert _count(db_session, system.id, "manual") == manual_before
