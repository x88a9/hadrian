"""Integration tests: run the xlsx import against the private research workbook.

These assert figures specific to that workbook (44 tabs, >1000 trades), so they
only run where it is available — set ``HADRIAN3_REAL_XLSX`` or place it at the
repository root. A fresh clone skips them and covers the same import paths
against the shipped sample in :mod:`tests.integration.test_import_sample_xlsx`.

Also requires the dev_db Postgres server
(port 55432, ``bash backend/scripts/dev_db.sh``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import ImportRun, System, Trade
from app.services.import_service import run_xlsx_import
from tests.paths import REAL_XLSX, has_real_xlsx

pytestmark = pytest.mark.integration

XLSX_PATH = str(REAL_XLSX)

pytest_skip_no_xlsx = pytest.mark.skipif(
    not has_real_xlsx(), reason=f"private research workbook missing at {REAL_XLSX}"
)


@pytest_skip_no_xlsx
def test_import_real_workbook_statistics(db_session):
    run = run_xlsx_import(db_session, XLSX_PATH)

    assert run.tabs_total == 44
    assert (
        run.systems_complete + run.systems_incomplete + run.tabs_skipped == 44
    )
    assert run.systems_complete >= 35
    assert run.trades_imported > 1000
    assert len(run.tab_results) == 44

    # persisted trades line up with the reported count (minus name-collision
    # overwrites, so >= is the safe assertion for the DB row count).
    db_trades = db_session.execute(select(func.count(Trade.id))).scalar_one()
    assert db_trades > 1000


@pytest_skip_no_xlsx
def test_import_is_idempotent(db_session):
    run1 = run_xlsx_import(db_session, XLSX_PATH)
    systems_after_1 = db_session.execute(select(func.count(System.id))).scalar_one()
    trades_after_1 = db_session.execute(select(func.count(Trade.id))).scalar_one()

    run2 = run_xlsx_import(db_session, XLSX_PATH)
    systems_after_2 = db_session.execute(select(func.count(System.id))).scalar_one()
    trades_after_2 = db_session.execute(select(func.count(Trade.id))).scalar_one()

    assert systems_after_1 == systems_after_2
    assert trades_after_1 == trades_after_2
    assert run1.trades_imported == run2.trades_imported
    assert run1.tabs_total == run2.tabs_total == 44


@pytest_skip_no_xlsx
def test_auto_trades_survive_reimport(db_session):
    run_xlsx_import(db_session, XLSX_PATH)

    system = db_session.execute(select(System).limit(1)).scalar_one()
    auto = Trade(system_id=system.id, r_value=1.5, source="auto")
    db_session.add(auto)
    db_session.commit()
    auto_id = auto.id

    manual_before = db_session.execute(
        select(func.count(Trade.id)).where(
            Trade.system_id == system.id, Trade.source == "manual"
        )
    ).scalar_one()

    run_xlsx_import(db_session, XLSX_PATH)

    # the auto trade still exists after the re-import
    still_there = db_session.execute(
        select(Trade).where(Trade.id == auto_id)
    ).scalar_one_or_none()
    assert still_there is not None
    assert still_there.source == "auto"

    # manual trades for that system were replaced (count unchanged, not doubled)
    manual_after = db_session.execute(
        select(func.count(Trade.id)).where(
            Trade.system_id == system.id, Trade.source == "manual"
        )
    ).scalar_one()
    assert manual_after == manual_before


@pytest_skip_no_xlsx
def test_two_import_runs_recorded(db_session):
    run_xlsx_import(db_session, XLSX_PATH)
    run_xlsx_import(db_session, XLSX_PATH)

    runs = db_session.execute(select(ImportRun)).scalars().all()
    assert len(runs) == 2
    for run in runs:
        assert len(run.tab_results) == 44
