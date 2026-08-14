"""Integration tests for the Phase-6 trade-write API (T4, D2/D4).

Covers source selection on ``POST /trades`` (default ``'auto'`` for client
compatibility, ``'ui'`` re-import-safe, ``'manual'`` rejected), ``PATCH``/``DELETE``
with win/loss re-derivation, on-the-fly metric recomputation (no cache) and the
re-import safety of ``ui`` trades. The importer parsers are monkeypatched so the
tests stay isolated from the real source files (mirrors
``test_reimport_protection.py``).

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


@pytest.fixture()
def system(db_session) -> int:
    sys = System(
        name="B-H1-801",
        prefix="B",
        timeframe="H1",
        status="backtest",
        import_status="complete",
    )
    db_session.add(sys)
    db_session.commit()
    return sys.id


def _trade_count(db_session, system_id: int) -> int:
    return db_session.execute(
        select(func.count(Trade.id)).where(Trade.system_id == system_id)
    ).scalar_one()


# --------------------------------------------------------------------------- #
# source selection on POST /trades
# --------------------------------------------------------------------------- #
def test_post_trade_default_source_is_auto(client, system):
    r = client.post("/trades", json={"system_id": system, "r_value": 2.0})
    assert r.status_code == 201
    assert r.json()["source"] == "auto"
    # win_loss derived from r_value.
    assert r.json()["win_loss"] == "win"


def test_post_trade_source_ui_persists(client, system, db_session):
    r = client.post(
        "/trades", json={"system_id": system, "r_value": -1.0, "source": "ui"}
    )
    assert r.status_code == 201
    assert r.json()["source"] == "ui"
    tid = r.json()["id"]
    assert db_session.get(Trade, tid).source == "ui"


def test_post_trade_source_manual_rejected(client, system):
    r = client.post(
        "/trades", json={"system_id": system, "r_value": 1.0, "source": "manual"}
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# metric recomputation (on-the-fly, no cache) around POST / PATCH / DELETE
# --------------------------------------------------------------------------- #
def _metrics(client, system_id: int) -> dict:
    return client.get(f"/systems/{system_id}").json()["metrics"]["all"]


def test_metrics_recompute_on_write(client, system):
    before = _metrics(client, system)
    assert before["total_trades"] == 0

    # POST two trades -> total_trades (COUNT of entry-bearing trades) and ev update.
    t1 = client.post(
        "/trades",
        json={"system_id": system, "entry": 100.0, "r_value": 2.0, "source": "ui"},
    ).json()
    client.post(
        "/trades",
        json={"system_id": system, "entry": 100.0, "r_value": -1.0, "source": "ui"},
    )

    after_post = _metrics(client, system)
    assert after_post["total_trades"] == 2
    assert after_post["ev"] == pytest.approx(0.5)  # (2 + -1) / 2

    # PATCH r_value -> ev recomputed, win_loss re-derived.
    p = client.patch(f"/trades/{t1['id']}", json={"r_value": 4.0})
    assert p.status_code == 200
    assert p.json()["win_loss"] == "win"
    after_patch = _metrics(client, system)
    assert after_patch["ev"] == pytest.approx(1.5)  # (4 + -1) / 2

    # DELETE one trade -> total_trades drops.
    d = client.delete(f"/trades/{t1['id']}")
    assert d.status_code == 204
    after_delete = _metrics(client, system)
    assert after_delete["total_trades"] == 1
    assert after_delete["ev"] == pytest.approx(-1.0)


def test_patch_trade_rvalue_rederives_win_loss(client, system, db_session):
    tid = client.post(
        "/trades", json={"system_id": system, "r_value": 2.0, "source": "ui"}
    ).json()["id"]
    # Set a losing r_value without win_loss -> re-derived to "loss".
    r = client.patch(f"/trades/{tid}", json={"r_value": -1.0})
    assert r.json()["win_loss"] == "loss"

    # Explicit win_loss is respected (not overwritten by derivation).
    r2 = client.patch(f"/trades/{tid}", json={"r_value": 3.0, "win_loss": "draw"})
    assert r2.json()["win_loss"] == "draw"


def test_patch_delete_trade_404(client, system):
    assert client.patch("/trades/99999", json={"r_value": 1.0}).status_code == 404
    assert client.delete("/trades/99999").status_code == 404


def test_list_trades_source_ui_filter(client, system):
    client.post("/trades", json={"system_id": system, "r_value": 1.0, "source": "ui"})
    client.post("/trades", json={"system_id": system, "r_value": 1.0, "source": "auto"})
    r = client.get("/trades", params={"system_id": system, "source": "ui"})
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert all(t["source"] == "ui" for t in r.json()["items"])


# --------------------------------------------------------------------------- #
# re-import safety: ui trades survive both importers
# --------------------------------------------------------------------------- #
def test_ui_trade_survives_xlsx_reimport(client, db_session, monkeypatch):
    """An ui-trade on an import-system with manual trades survives an xlsx
    re-import (which replaces the manual trades but never the ui trade)."""
    sys = System(
        name="B-H1-500",
        prefix="B",
        timeframe="H1",
        origin="import",
        import_status="complete",
    )
    db_session.add(sys)
    db_session.commit()
    sid = sys.id

    db_session.add(Trade(system_id=sid, r_value=1.0, win_loss="win", source="manual"))
    client.post("/trades", json={"system_id": sid, "r_value": 5.0, "source": "ui"})
    db_session.commit()

    def fake_parse_workbook(path):  # noqa: ARG001
        return ParseResult(tabs=[
            ParsedTab(
                tab_name="B-H1-500",
                system_name="B-H1-500",
                entry_rule="e",
                trades=[ParsedTrade(r_value=2.0, win_loss="win")],
                parse_status="complete",
            )
        ])

    monkeypatch.setattr(
        "app.services.import_service.parse_workbook", fake_parse_workbook
    )
    run_xlsx_import(db_session, "dummy.xlsx")

    # manual trade replaced by the one tab trade; ui trade untouched.
    sources = db_session.execute(
        select(Trade.source, Trade.r_value).where(Trade.system_id == sid)
    ).all()
    ui = [s for s in sources if s.source == "ui"]
    assert len(ui) == 1
    assert ui[0].r_value == 5.0
    assert sum(1 for s in sources if s.source == "manual") == 1  # the tab trade


def test_ui_trade_survives_programmatic_reimport(
    client, db_session, monkeypatch, tmp_path
):
    sys = System(
        name="B-H1-600",
        prefix="B",
        timeframe="H1",
        origin="import",
        provenance="programmatic",
        source_engine="hadrian2",
        import_status="complete",
    )
    db_session.add(sys)
    db_session.commit()
    sid = sys.id

    db_session.add(Trade(system_id=sid, r_value=1.0, win_loss="win", source="auto"))
    client.post("/trades", json={"system_id": sid, "r_value": 7.0, "source": "ui"})
    db_session.commit()

    def fake_hadrian2(directory):  # noqa: ARG001
        return [
            ParsedProgrammaticSystem(
                name="B-H1-600",
                source_engine="hadrian2",
                entry_rule="e",
                trades=[ParsedTrade(r_value=2.0, win_loss="win")],
                parse_status="complete",
            )
        ]

    monkeypatch.setattr(
        "app.services.import_service.parse_hadrian2", fake_hadrian2
    )
    monkeypatch.setattr(
        "app.services.import_service.parse_hadrian_engine", lambda d: []
    )

    dir_a = tmp_path / "h2"
    dir_b = tmp_path / "engine"
    dir_a.mkdir()
    dir_b.mkdir()
    run_programmatic_import(db_session, str(dir_a), str(dir_b))

    sources = db_session.execute(
        select(Trade.source, Trade.r_value).where(Trade.system_id == sid)
    ).all()
    ui = [s for s in sources if s.source == "ui"]
    assert len(ui) == 1
    assert ui[0].r_value == 7.0
    assert sum(1 for s in sources if s.source == "auto") == 1  # replaced auto trade
