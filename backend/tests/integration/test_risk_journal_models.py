"""Integration tests for RiskRule / journal models + GET /risk-rules (T4)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import get_db
from app.main import app
from app.models import DailyRiskLog, JournalEntry, RiskRule, System, Trade

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_risk_rule_roundtrip(db_session):
    system = System(name="B-H1-050", prefix="B", timeframe="H1", import_status="complete")
    db_session.add(system)
    db_session.flush()
    rule = RiskRule(
        name="tight",
        system_id=system.id,
        max_daily_r=2.0,
        max_trades_per_day=5,
        notes="scoped override",
    )
    db_session.add(rule)
    db_session.commit()

    stored = db_session.execute(
        select(RiskRule).where(RiskRule.name == "tight")
    ).scalar_one()
    assert stored.system_id == system.id
    assert stored.max_daily_r == 2.0
    assert stored.active is True
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_journal_entry_roundtrip(db_session):
    entry = JournalEntry(
        entry_date=date(2025, 6, 1),
        entry_type="daily_review",
        title="Good day",
        body="Followed the plan.",
        tags=["discipline", "win"],
    )
    db_session.add(entry)
    db_session.commit()

    stored = db_session.execute(select(JournalEntry)).scalar_one()
    assert stored.entry_type == "daily_review"
    assert stored.tags == ["discipline", "win"]
    assert stored.created_at is not None


def test_daily_risk_log_unique_date(db_session):
    db_session.add(DailyRiskLog(log_date=date(2025, 6, 2), realized_r=1.5, trade_count=3))
    db_session.commit()
    db_session.add(DailyRiskLog(log_date=date(2025, 6, 2), realized_r=0.0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_fk_set_null_on_system_delete(db_session):
    system = System(name="B-H1-051", prefix="B", timeframe="H1", import_status="complete")
    db_session.add(system)
    db_session.flush()
    rule = RiskRule(name="scoped", system_id=system.id)
    entry = JournalEntry(
        entry_date=date(2025, 6, 3), entry_type="note", system_id=system.id
    )
    db_session.add_all([rule, entry])
    db_session.commit()

    db_session.query(System).filter(System.name == "B-H1-051").delete(
        synchronize_session=False
    )
    db_session.commit()

    db_session.expire_all()
    assert db_session.execute(select(RiskRule).where(RiskRule.name == "scoped")).scalar_one().system_id is None
    assert db_session.execute(select(JournalEntry)).scalar_one().system_id is None


def test_journal_trade_fk_set_null_on_trade_delete(db_session):
    system = System(name="B-H1-052", prefix="B", timeframe="H1", import_status="complete")
    system.trades = [Trade(r_value=1.0, source="manual")]
    db_session.add(system)
    db_session.commit()
    trade_id = system.trades[0].id

    entry = JournalEntry(
        entry_date=date(2025, 6, 4), entry_type="trade_review", trade_id=trade_id
    )
    db_session.add(entry)
    db_session.commit()

    db_session.query(Trade).filter(Trade.id == trade_id).delete(
        synchronize_session=False
    )
    db_session.commit()
    db_session.expire_all()
    assert db_session.execute(select(JournalEntry)).scalar_one().trade_id is None


def test_daily_risk_log_rule_fk_set_null(db_session):
    rule = RiskRule(name="ref")
    db_session.add(rule)
    db_session.flush()
    db_session.add(
        DailyRiskLog(log_date=date(2025, 6, 5), risk_rule_id=rule.id, halted=True)
    )
    db_session.commit()

    db_session.query(RiskRule).filter(RiskRule.name == "ref").delete(
        synchronize_session=False
    )
    db_session.commit()
    db_session.expire_all()
    log = db_session.execute(select(DailyRiskLog)).scalar_one()
    assert log.risk_rule_id is None
    assert log.halted is True


def test_get_risk_rules_returns_default(client, db_session):
    # The default rule is seeded by migration 0004; the truncating db_session
    # fixture wipes it, so re-seed to mirror the migration for this endpoint test.
    db_session.add(
        RiskRule(name="default", max_daily_r=3, max_weekly_r=5, active=True)
    )
    db_session.commit()

    r = client.get("/risk-rules")
    assert r.status_code == 200
    items = r.json()["items"]
    default = next(i for i in items if i["name"] == "default")
    assert default["max_daily_r"] == 3
    assert default["max_weekly_r"] == 5
    assert default["active"] is True
