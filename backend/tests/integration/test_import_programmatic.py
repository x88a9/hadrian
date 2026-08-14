"""Integration tests for the programmatic import (Phase 5, T4 / D2, D3).

Runs the real Hadrian² + Hadrian_Engine source directories against the dev_db
Postgres server (Port 55432). Auto-skipped when the server or the source
directories are missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_db
from app.main import app
from app.models import ParameterSweep, System, Trade
from app.services.import_service import run_programmatic_import, run_xlsx_import

pytestmark = pytest.mark.integration

from tests.paths import (
    ENGINE_DIR,
    HADRIAN2_DIR,
    REAL_XLSX,
    SAMPLE_XLSX,
    has_engine_sources,
    has_real_xlsx,
)

XLSX_PATH = str(REAL_XLSX if has_real_xlsx() else SAMPLE_XLSX)

skip_no_sources = pytest.mark.skipif(
    not has_engine_sources(),
    reason="programmatic source dirs unset (HADRIAN2_RESULTS_DIR / "
    "HADRIAN_ENGINE_RESULTS_DIR)",
)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _count(session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def _prog_systems(session):
    return session.execute(
        select(System).where(System.provenance == "programmatic")
    ).scalars().all()


@skip_no_sources
def test_programmatic_import_statistics(db_session):
    run = run_programmatic_import(db_session, HADRIAN2_DIR, ENGINE_DIR)

    # 32 programmatic systems: 13 hadrian2 + 19 hadrian_engine.
    prog = _prog_systems(db_session)
    assert len(prog) == 32
    by_engine: dict[str, int] = {}
    for s in prog:
        by_engine[s.source_engine] = by_engine.get(s.source_engine, 0) + 1
    assert by_engine == {"hadrian2": 13, "hadrian_engine": 19}
    assert all(s.provenance == "programmatic" for s in prog)

    # All programmatic trades are source='auto'.
    total_auto = db_session.execute(
        select(func.count(Trade.id)).where(Trade.source == "auto")
    ).scalar_one()
    assert total_auto > 7000

    h2_ids = [s.id for s in prog if s.source_engine == "hadrian2"]
    h2_auto = db_session.execute(
        select(func.count(Trade.id)).where(
            Trade.system_id.in_(h2_ids), Trade.source == "auto"
        )
    ).scalar_one()
    assert h2_auto == 2151

    # Sweeps: exactly 124 rows / 2284 points.
    sweeps = db_session.execute(select(ParameterSweep)).scalars().all()
    assert len(sweeps) == 124
    assert sum(len(s.points or []) for s in sweeps) == 2284

    # ImportRun bookkeeping.
    assert run.tabs_total == 32
    assert run.systems_complete + run.systems_incomplete == 32
    assert run.trades_imported == total_auto
    assert run.file_path == f"hadrian2:{HADRIAN2_DIR}; hadrian_engine:{ENGINE_DIR}"
    assert len(run.tab_results) == 32


@skip_no_sources
def test_programmatic_import_is_idempotent(db_session):
    run_programmatic_import(db_session, HADRIAN2_DIR, ENGINE_DIR)
    systems_1 = _count(db_session, System)
    trades_1 = _count(db_session, Trade)
    sweeps_1 = _count(db_session, ParameterSweep)

    run_programmatic_import(db_session, HADRIAN2_DIR, ENGINE_DIR)
    systems_2 = _count(db_session, System)
    trades_2 = _count(db_session, Trade)
    sweeps_2 = _count(db_session, ParameterSweep)

    assert (systems_1, trades_1, sweeps_1) == (systems_2, trades_2, sweeps_2)
    assert systems_2 == 32
    assert sweeps_2 == 124


@skip_no_sources
def test_coexistence_with_xlsx(db_session):
    if not Path(XLSX_PATH).is_file():
        pytest.skip(f"canonical xlsx missing at {XLSX_PATH}")

    # xlsx first, then programmatic.
    run_xlsx_import(db_session, XLSX_PATH)
    manual_systems_before = db_session.execute(
        select(func.count(System.id)).where(System.provenance == "manual")
    ).scalar_one()
    manual_trades_before = db_session.execute(
        select(func.count(Trade.id)).where(Trade.source == "manual")
    ).scalar_one()
    assert manual_systems_before > 0
    assert manual_trades_before > 0

    run_programmatic_import(db_session, HADRIAN2_DIR, ENGINE_DIR)

    # Programmatic import left manual systems/trades untouched.
    manual_systems_after = db_session.execute(
        select(func.count(System.id)).where(System.provenance == "manual")
    ).scalar_one()
    manual_trades_after = db_session.execute(
        select(func.count(Trade.id)).where(Trade.source == "manual")
    ).scalar_one()
    assert manual_systems_after == manual_systems_before
    assert manual_trades_after == manual_trades_before
    assert len(_prog_systems(db_session)) == 32

    # Now re-run the xlsx import: programmatic systems/trades survive.
    prog_ids_before = {s.id for s in _prog_systems(db_session)}
    auto_before = db_session.execute(
        select(func.count(Trade.id)).where(Trade.source == "auto")
    ).scalar_one()

    run_xlsx_import(db_session, XLSX_PATH)

    prog = _prog_systems(db_session)
    assert {s.id for s in prog} == prog_ids_before
    assert all(s.provenance == "programmatic" for s in prog)
    auto_after = db_session.execute(
        select(func.count(Trade.id)).where(Trade.source == "auto")
    ).scalar_one()
    assert auto_after == auto_before


def test_programmatic_missing_both_dirs_404(client, tmp_path):
    missing_a = str(tmp_path / "does_not_exist_a")
    missing_b = str(tmp_path / "does_not_exist_b")
    r = client.post(
        "/import/programmatic",
        json={"hadrian2_path": missing_a, "engine_path": missing_b},
    )
    assert r.status_code == 404
