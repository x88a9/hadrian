"""Shared fixtures for integration tests (Phase 7).

The session-level ``db_session`` fixture TRUNCATEs every table before each test,
which also wipes the migration seeds (venue / asset settings / initial balance).
Live-trade tests therefore re-seed via ``seed_live`` with the same verified
values the migration seeds (Entry 0.0144 %, Exit 0.0432 %, min 0.00001, buffer
0.1, ±5 %, start balance 324.00).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import AccountBalance, AssetSetting, System, Venue


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def live_system(db_session) -> int:
    sys = System(
        name="B-H1-801",
        prefix="B",
        timeframe="H1",
        status="active",
        import_status="complete",
    )
    db_session.add(sys)
    db_session.commit()
    return sys.id


@pytest.fixture()
def seed_live(db_session):
    """Seed one venue + asset-settings versions + initial balance 324.00.

    Assets tragen die echten Hyperliquid-Werte (Lot-Size = 10^-szDecimals,
    ganzzahlige max_leverage), damit Tests die asset-spezifische Granularität
    wirklich prüfen: DEFAULT/BTC 0.00001, SOL 0.01, DOT 0.1.
    """
    venue = Venue(name="CEX", notes="test venue")
    db_session.add(venue)
    db_session.flush()

    def _setting(asset: str, lot: float, max_lev: float | None) -> AssetSetting:
        return AssetSetting(
            venue_id=venue.id,
            asset=asset,
            entry_fee_pct=0.000144,
            exit_fee_pct=0.000432,
            min_position_size=lot,
            leverage_buffer=0.1,
            upside_deviation_allowed_pct=0.05,
            downside_deviation_allowed_pct=0.05,
            max_leverage=max_lev,
            leverage_step=1.0,
            min_order_value_usd=10.0,
            valid_from=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )

    setting = _setting("DEFAULT", 0.00001, None)
    db_session.add_all(
        [
            setting,
            _setting("BTC", 0.00001, 40),
            _setting("SOL", 0.01, 20),
            _setting("DOT", 0.1, 10),
        ]
    )
    db_session.add(
        AccountBalance(balance=324.00, change_type="initial", note="seed")
    )
    db_session.commit()
    return {"venue_id": venue.id, "setting_id": setting.id}
