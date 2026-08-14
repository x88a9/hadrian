from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Concept, ImportRun, ParameterSweep, System, SystemConcept, Trade

pytestmark = pytest.mark.integration


def _make_system(name: str = "B-H1-801") -> System:
    return System(
        name=name,
        prefix="B",
        timeframe="H1",
        status="backtest",
        entry_rule="Break of prior high",
        sl_rule="Below structure",
        tp_rule="2R fixed",
        import_status="complete",
        reported_metrics={"ev": 0.41, "total_r": 50.4},
    )


def test_insert_and_read_system_trade_importrun(db_session):
    system = _make_system()
    system.trades = [
        Trade(
            trade_datetime=datetime(2025, 3, 4, 15, 0),
            zone="NY AM",
            timeframe="H1",
            entry=64123.5,
            sl=63900.0,
            exit=64800.0,
            direction="long",
            r_value=2.1,
            win_loss="win",
            source="manual",
        ),
        Trade(r_value=-1.0, direction="short", win_loss="loss", source="manual"),
    ]
    db_session.add(system)

    run = ImportRun(
        file_path="/tmp/repo.xlsx",
        tabs_total=44,
        systems_complete=37,
        systems_incomplete=7,
        tabs_skipped=0,
        trades_imported=2,
        tab_results=[{"tab": "B-H1-801", "status": "complete", "trades": 2}],
    )
    db_session.add(run)
    db_session.commit()

    stored = db_session.execute(
        select(System).where(System.name == "B-H1-801")
    ).scalar_one()
    assert stored.id is not None
    assert stored.created_at is not None
    assert stored.updated_at is not None
    assert stored.reported_metrics == {"ev": 0.41, "total_r": 50.4}
    assert len(stored.trades) == 2

    first = sorted(stored.trades, key=lambda t: t.id)[0]
    assert first.direction == "long"
    assert first.r_value == 2.1
    assert first.trade_datetime == datetime(2025, 3, 4, 15, 0)

    stored_run = db_session.execute(select(ImportRun)).scalar_one()
    assert stored_run.tabs_total == 44
    assert stored_run.tab_results[0]["tab"] == "B-H1-801"
    assert stored_run.started_at is not None


def test_system_origin_and_overrides_defaults(db_session):
    """Phase 6 (0006): a plain System defaults to origin='import' / empty
    user_overrides; a Trade with source='ui' persists (VARCHAR(6) fits 'ui')."""
    system = _make_system("EMA-H4-042")
    db_session.add(system)
    db_session.flush()
    db_session.add(Trade(system_id=system.id, r_value=1.2, source="ui"))
    db_session.commit()

    stored = db_session.execute(
        select(System).where(System.name == "EMA-H4-042")
    ).scalar_one()
    assert stored.origin == "import"
    assert stored.user_overrides == []

    ui_trade = db_session.execute(
        select(Trade).where(Trade.system_id == stored.id, Trade.source == "ui")
    ).scalar_one()
    assert ui_trade.r_value == 1.2

    # Overrides are a real JSONB list roundtrip.
    stored.user_overrides = ["entry_rule", "tp_rule"]
    db_session.commit()
    reloaded = db_session.execute(
        select(System).where(System.name == "EMA-H4-042")
    ).scalar_one()
    assert reloaded.user_overrides == ["entry_rule", "tp_rule"]


def test_unique_constraint_on_name(db_session):
    db_session.add(_make_system("MR-M15-802"))
    db_session.commit()

    db_session.add(_make_system("MR-M15-802"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_parameter_sweep_roundtrip(db_session):
    system = _make_system("VP-M5-010")
    db_session.add(system)
    db_session.flush()

    points = [
        {"x": 1.0, "y": 0.5, "value": 0.31},
        {"x": 2.0, "y": 1.0, "value": 0.44},
    ]
    sweep = ParameterSweep(
        system_id=system.id,
        label="tp/sl grid",
        points=points,
    )
    db_session.add(sweep)
    db_session.commit()

    stored = db_session.execute(select(ParameterSweep)).scalar_one()
    assert stored.id is not None
    assert stored.system_id == system.id
    assert stored.label == "tp/sl grid"
    # server-side defaults for the generic axes/metric
    assert stored.param_x == "tp_r"
    assert stored.param_y == "sl_r"
    assert stored.metric == "ev"
    assert stored.created_at is not None
    assert len(stored.points) == 2
    assert stored.points[1]["value"] == 0.44


def test_parameter_sweep_cascade_delete(db_session):
    system = _make_system("VP-M5-011")
    db_session.add(system)
    db_session.flush()
    db_session.add(ParameterSweep(system_id=system.id, points=[{"x": 1, "y": 1, "value": 0.1}]))
    db_session.commit()

    db_session.query(System).filter(System.name == "VP-M5-011").delete(
        synchronize_session=False
    )
    db_session.commit()
    assert db_session.execute(select(ParameterSweep)).scalars().all() == []


def test_concept_assignment_roundtrip(db_session):
    system = _make_system("VP-M5-020")
    concept = Concept(name="Volume Profile", description="VP concept")
    db_session.add_all([system, concept])
    db_session.flush()

    db_session.add(
        SystemConcept(
            system_id=system.id, concept_id=concept.id, source="manual"
        )
    )
    db_session.commit()

    stored = db_session.execute(select(SystemConcept)).scalar_one()
    assert stored.system_id == system.id
    assert stored.concept_id == concept.id
    assert stored.source == "manual"
    assert stored.created_at is not None

    # relationship navigation
    stored_concept = db_session.execute(
        select(Concept).where(Concept.name == "Volume Profile")
    ).scalar_one()
    assert len(stored_concept.system_links) == 1


def test_concept_name_unique(db_session):
    db_session.add(Concept(name="Funding"))
    db_session.commit()
    db_session.add(Concept(name="Funding"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_system_concept_unique(db_session):
    system = _make_system("MR-M15-030")
    concept = Concept(name="Liquidity")
    db_session.add_all([system, concept])
    db_session.flush()
    db_session.add(SystemConcept(system_id=system.id, concept_id=concept.id))
    db_session.commit()
    db_session.add(SystemConcept(system_id=system.id, concept_id=concept.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_system_concept_cascade_on_system_delete(db_session):
    system = _make_system("B-H1-040")
    concept = Concept(name="Order Flow")
    db_session.add_all([system, concept])
    db_session.flush()
    db_session.add(SystemConcept(system_id=system.id, concept_id=concept.id))
    db_session.commit()

    db_session.query(System).filter(System.name == "B-H1-040").delete(
        synchronize_session=False
    )
    db_session.commit()

    # Assignment gone, concept survives (only the system cascade fires).
    assert db_session.execute(select(SystemConcept)).scalars().all() == []
    assert db_session.execute(select(Concept)).scalars().all()


def test_cascade_delete_removes_trades(db_session):
    system = _make_system("REV-H4-801")
    system.trades = [Trade(r_value=1.0, source="manual"), Trade(r_value=-1.0, source="manual")]
    db_session.add(system)
    db_session.commit()

    assert db_session.execute(select(Trade)).scalars().all()

    # DB-seitiges Cascade (ondelete=CASCADE) pruefen: direktes SQL-Delete.
    db_session.query(System).filter(System.name == "REV-H4-801").delete(
        synchronize_session=False
    )
    db_session.commit()

    assert db_session.execute(select(System)).scalars().all() == []
    assert db_session.execute(select(Trade)).scalars().all() == []
