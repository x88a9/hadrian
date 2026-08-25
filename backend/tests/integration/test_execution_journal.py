"""The execution journal: every order, in any mode, including the refused ones.

The journal is what makes a fortnight of dry running comparable with what
actually happened on the testnet afterwards, so a dry-run row has to be as
complete as a real one — and unmistakably marked as simulated.
"""

from __future__ import annotations

import pytest
import sqlalchemy

from app.execution.mode import ExecutionMode, MainnetDisabled
from app.execution.orders import OrderIntent, OrderReceipt
from app.execution.sizing import StageNotTradeable
from app.models import ExecutionOrder, System
from app.models.execution_order import EXECUTION_ORDER_MODES
from app.services.execution_service import execute_signal

SIGNAL = dict(
    direction="long",
    entry_price=109000.0,
    stop_price=109900.0,
    desired_risk_usd=3.0,
    portfolio_size=324.0,
)


def make_system(db_session, status: str = "active", name: str = "B-H1-901") -> System:
    system = System(
        name=name,
        asset="BTC",
        timeframe="1h",
        status=status,
        provenance="engine",
        origin="ui",
        import_status="complete",
    )
    db_session.add(system)
    db_session.commit()
    return system


class ExplodingExecutor:
    mode = ExecutionMode.DRY_RUN

    def place(self, intent: OrderIntent) -> OrderReceipt:
        raise RuntimeError("the venue connection dropped")


def test_a_dry_run_signal_is_journalled_in_full(db_session, seed_live):
    system = make_system(db_session)
    row = execute_signal(
        db_session, system=system, setting=None, mode=ExecutionMode.DRY_RUN, **SIGNAL
    )

    assert row.mode == "dry_run"
    assert row.status == "simulated"
    assert row.accepted is True
    assert row.asset == "BTC"
    assert row.stage == "active"
    assert row.stage_scale == 1.0
    assert row.size == 0.00312, "the verified reference size reached the journal"
    assert row.realised_risk_usd == pytest.approx(3.00388608, abs=1e-9)
    assert row.system_id == system.id
    assert row.intent["client_id"] == row.client_id
    assert row.receipt["mode"] == "dry_run"


def test_a_dry_run_row_carries_no_venue_order_id(db_session, seed_live):
    system = make_system(db_session)
    row = execute_signal(
        db_session, system=system, setting=None, mode=ExecutionMode.DRY_RUN, **SIGNAL
    )
    assert row.venue_order_id is None, (
        "a simulated row with a venue id would be indistinguishable from a real one"
    )


def test_a_system_at_backtest_stage_writes_nothing(db_session, seed_live):
    """A stage error is a caller mistake, not an order outcome; journalling it
    would suggest something was attempted."""
    system = make_system(db_session, status="backtest")

    with pytest.raises(StageNotTradeable):
        execute_signal(
            db_session, system=system, setting=None, mode=ExecutionMode.DRY_RUN, **SIGNAL
        )

    assert db_session.scalars(sqlalchemy.select(ExecutionOrder)).all() == []


def test_live_testing_journals_the_reduced_size(db_session, seed_live):
    system = make_system(db_session, status="live_testing")
    row = execute_signal(
        db_session, system=system, setting=None, mode=ExecutionMode.DRY_RUN, **SIGNAL
    )

    assert row.stage_scale == 0.25
    assert row.requested_risk_usd == 3.0
    assert row.realised_risk_usd < 1.0


def test_an_untradeable_size_is_journalled_without_calling_the_executor(
    db_session, seed_live
):
    """Discovering this from an exchange error would mean sending an order that
    was never going to work."""
    system = make_system(db_session)
    row = execute_signal(
        db_session,
        system=system,
        setting=None,
        mode=ExecutionMode.DRY_RUN,
        executor=ExplodingExecutor(),
        direction="long",
        entry_price=109000.0,
        stop_price=109900.0,
        desired_risk_usd=0.0001,
        portfolio_size=324.0,
    )

    assert row.accepted is False
    assert row.status == "rejected"
    assert "not sent" in row.message
    assert "rounds to zero" in row.message


def test_an_executor_failure_is_journalled_and_then_raised(db_session, seed_live):
    """An order that failed is exactly the kind that needs a record — and the
    caller still has to hear about it."""
    system = make_system(db_session)

    with pytest.raises(RuntimeError, match="connection dropped"):
        execute_signal(
            db_session,
            system=system,
            setting=None,
            mode=ExecutionMode.DRY_RUN,
            executor=ExplodingExecutor(),
            **SIGNAL,
        )

    rows = db_session.scalars(sqlalchemy.select(ExecutionOrder)).all()
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert "connection dropped" in rows[0].message


def test_mainnet_cannot_reach_the_journal(db_session, seed_live):
    system = make_system(db_session)

    with pytest.raises(MainnetDisabled):
        execute_signal(
            db_session,
            system=system,
            setting=None,
            mode=ExecutionMode.MAINNET,
            **SIGNAL,
        )

    assert db_session.scalars(sqlalchemy.select(ExecutionOrder)).all() == []


def test_the_journal_vocabulary_admits_no_mainnet_row():
    """A history that could contain such a row would be ambiguous about whether
    this build ever traded real money."""
    assert set(EXECUTION_ORDER_MODES) == {"dry_run", "testnet"}


def test_the_default_mode_is_used_when_none_is_given(db_session, seed_live):
    from app.core.config import settings

    system = make_system(db_session)
    row = execute_signal(db_session, system=system, setting=None, **SIGNAL)

    assert settings.EXECUTION_MODE is ExecutionMode.DRY_RUN
    assert row.mode == "dry_run"


def test_asset_settings_drive_the_lot_size(db_session, seed_live):
    """SOL trades in hundredths, BTC in hundred-thousandths; using the wrong
    step produces a size the venue cannot accept."""
    from app.models import AssetSetting

    sol = db_session.scalar(
        sqlalchemy.select(AssetSetting).where(AssetSetting.asset == "SOL")
    )
    system = make_system(db_session, name="B-H1-902")
    system.asset = "SOL"
    db_session.commit()

    row = execute_signal(
        db_session,
        system=system,
        setting=sol,
        mode=ExecutionMode.DRY_RUN,
        direction="long",
        entry_price=200.0,
        stop_price=190.0,
        desired_risk_usd=20.0,
        portfolio_size=324.0,
    )

    assert row.size == round(row.size, 2), "SOL sizes must land on the 0.01 grid"
