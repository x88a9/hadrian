"""Integration tests for the Phase-6 re-import protection (T2, D1/D2).

Verifies that UI-created systems (``origin='ui'``) are fully skipped by the xlsx
and programmatic importers, that field-level ``user_overrides`` are respected on
``origin='import'`` systems, and that ``POST /systems`` sets ``origin='ui'`` on
creation and grows ``user_overrides`` on update. The importer parsers are
monkeypatched so the tests stay isolated from the real source files.

Runs against the dev_db Postgres server (Port 55432, hadrian3_test). Auto-skipped
when the server is missing (see tests/conftest.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_db
from app.importers.xlsx import ParsedTab, ParsedTrade, ParseResult
from app.importers.programmatic_types import ParsedProgrammaticSystem
from app.main import app
from app.models import System, Trade
from app.services.import_service import (
    run_programmatic_import,
    run_xlsx_import,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _get_system(db_session, name: str) -> System:
    return db_session.execute(
        select(System).where(System.name == name)
    ).scalar_one()


def _trade_count(db_session, system_id: int) -> int:
    return db_session.execute(
        select(func.count(Trade.id)).where(Trade.system_id == system_id)
    ).scalar_one()


# --------------------------------------------------------------------------- #
# a) UI-System survives an xlsx re-import untouched
# --------------------------------------------------------------------------- #
def test_xlsx_reimport_skips_ui_system(client, db_session, monkeypatch):
    r = client.post(
        "/systems",
        json={
            "name": "B-H1-999",
            "entry_rule": "UI entry",
            "sl_rule": "UI sl",
            "tp_rule": "UI tp",
            "notes": "UI note",
        },
    )
    assert r.status_code == 201
    assert r.json()["origin"] == "ui"

    system = _get_system(db_session, "B-H1-999")
    db_session.add(
        Trade(system_id=system.id, r_value=3.0, direction="long",
              win_loss="win", source="ui")
    )
    db_session.commit()
    sid = system.id

    def fake_parse_workbook(path):  # noqa: ARG001
        return ParseResult(tabs=[
            ParsedTab(
                tab_name="B-H1-999",
                system_name="B-H1-999",
                entry_rule="IMPORT entry",
                sl_rule="IMPORT sl",
                tp_rule="IMPORT tp",
                reported_metrics={"ev": 9.9},
                trades=[ParsedTrade(r_value=1.0, win_loss="win")],
                parse_status="complete",
            )
        ])

    monkeypatch.setattr(
        "app.services.import_service.parse_workbook", fake_parse_workbook
    )
    run = run_xlsx_import(db_session, "dummy.xlsx")

    # System fields untouched (UI values preserved).
    system = _get_system(db_session, "B-H1-999")
    assert system.origin == "ui"
    assert system.entry_rule == "UI entry"
    assert system.sl_rule == "UI sl"
    assert system.tp_rule == "UI tp"
    assert system.notes == "UI note"
    assert system.reported_metrics != {"ev": 9.9}

    # Trades untouched: still exactly the one ui trade, no import trade added.
    assert _trade_count(db_session, sid) == 1
    only = db_session.execute(
        select(Trade).where(Trade.system_id == sid)
    ).scalar_one()
    assert only.source == "ui"

    # Skip is logged visibly.
    assert run.tabs_skipped == 1
    skipped = [t for t in run.tab_results if t["status"] == "skipped"]
    assert len(skipped) == 1
    assert "protected" in skipped[0]["message"]
    assert skipped[0]["system_name"] == "B-H1-999"


# --------------------------------------------------------------------------- #
# b) UI-System survives a programmatic re-import untouched
# --------------------------------------------------------------------------- #
def test_programmatic_reimport_skips_ui_system(
    client, db_session, monkeypatch, tmp_path
):
    r = client.post(
        "/systems",
        json={"name": "B-H1-888", "entry_rule": "UI entry", "tp_rule": "UI tp"},
    )
    assert r.status_code == 201

    system = _get_system(db_session, "B-H1-888")
    db_session.add(
        Trade(system_id=system.id, r_value=2.0, direction="short",
              win_loss="win", source="ui")
    )
    db_session.commit()
    sid = system.id

    def fake_hadrian2(directory):  # noqa: ARG001
        return [
            ParsedProgrammaticSystem(
                name="B-H1-888",
                source_engine="hadrian2",
                entry_rule="IMPORT entry",
                tp_rule="IMPORT tp",
                trades=[ParsedTrade(r_value=1.0, win_loss="win")],
                parse_status="complete",
            )
        ]

    def fake_engine(directory):  # noqa: ARG001
        return []

    monkeypatch.setattr(
        "app.services.import_service.parse_hadrian2", fake_hadrian2
    )
    monkeypatch.setattr(
        "app.services.import_service.parse_hadrian_engine", fake_engine
    )

    dir_a = tmp_path / "h2"
    dir_b = tmp_path / "engine"
    dir_a.mkdir()
    dir_b.mkdir()

    run = run_programmatic_import(db_session, str(dir_a), str(dir_b))

    system = _get_system(db_session, "B-H1-888")
    assert system.origin == "ui"
    assert system.entry_rule == "UI entry"
    assert system.tp_rule == "UI tp"
    assert system.provenance != "programmatic"

    assert _trade_count(db_session, sid) == 1
    only = db_session.execute(
        select(Trade).where(Trade.system_id == sid)
    ).scalar_one()
    assert only.source == "ui"

    assert run.tabs_skipped == 1
    skipped = [t for t in run.tab_results if t["status"] == "skipped"]
    assert len(skipped) == 1
    assert "protected" in skipped[0]["message"]


# --------------------------------------------------------------------------- #
# c) Field-level override on an import system: entry_rule kept, tp_rule replaced
# --------------------------------------------------------------------------- #
def test_field_override_on_import_system(client, db_session, monkeypatch):
    db_session.add(
        System(
            name="B-H1-777",
            prefix="B",
            timeframe="H1",
            origin="import",
            import_status="complete",
            entry_rule="orig entry",
            sl_rule="orig sl",
            tp_rule="orig tp",
        )
    )
    db_session.commit()

    # User edits entry_rule via the UI -> tracked as an override.
    r = client.post("/systems", json={"name": "B-H1-777", "entry_rule": "user entry"})
    assert r.status_code == 200
    assert r.json()["origin"] == "import"  # origin unchanged on update
    assert "entry_rule" in r.json()["user_overrides"]

    def fake_parse_workbook(path):  # noqa: ARG001
        return ParseResult(tabs=[
            ParsedTab(
                tab_name="B-H1-777",
                system_name="B-H1-777",
                entry_rule="import entry",
                sl_rule="import sl",
                tp_rule="import tp",
                parse_status="complete",
            )
        ])

    monkeypatch.setattr(
        "app.services.import_service.parse_workbook", fake_parse_workbook
    )
    run = run_xlsx_import(db_session, "dummy.xlsx")

    system = _get_system(db_session, "B-H1-777")
    # entry_rule protected (in user_overrides), everything else re-imported.
    assert system.entry_rule == "user entry"
    assert system.tp_rule == "import tp"
    assert system.sl_rule == "import sl"
    assert run.tabs_skipped == 0  # import system is upserted, not skipped


# --------------------------------------------------------------------------- #
# d) POST /systems: origin='ui' on create, user_overrides grow on update
# --------------------------------------------------------------------------- #
def test_post_systems_origin_and_override_growth(client, db_session):
    r = client.post("/systems", json={"name": "MR-M15-555", "entry_rule": "e"})
    assert r.status_code == 201
    body = r.json()
    assert body["origin"] == "ui"
    assert _get_system(db_session, "MR-M15-555").origin == "ui"

    r2 = client.post(
        "/systems",
        json={"name": "MR-M15-555", "entry_rule": "e2", "sl_rule": "s"},
    )
    assert r2.status_code == 200
    overrides = set(r2.json()["user_overrides"])
    assert {"entry_rule", "sl_rule"} <= overrides

    r3 = client.post("/systems", json={"name": "MR-M15-555", "tp_rule": "t"})
    assert r3.status_code == 200
    overrides = r3.json()["user_overrides"]
    assert set(overrides) == {"entry_rule", "sl_rule", "tp_rule"}
    # No duplicates accumulated.
    assert len(overrides) == len(set(overrides))


# --------------------------------------------------------------------------- #
# e) Regression: a plain import without UI systems is unchanged (no skips)
# --------------------------------------------------------------------------- #
def test_import_without_ui_systems_unchanged(db_session, monkeypatch):
    def fake_parse_workbook(path):  # noqa: ARG001
        return ParseResult(tabs=[
            ParsedTab(
                tab_name="B-H1-100",
                system_name="B-H1-100",
                entry_rule="import entry",
                trades=[ParsedTrade(r_value=1.0, win_loss="win")],
                parse_status="complete",
            )
        ])

    monkeypatch.setattr(
        "app.services.import_service.parse_workbook", fake_parse_workbook
    )
    run = run_xlsx_import(db_session, "dummy.xlsx")

    assert run.tabs_skipped == 0
    system = _get_system(db_session, "B-H1-100")
    assert system.origin == "import"
    assert system.entry_rule == "import entry"
    assert list(system.user_overrides or []) == []
