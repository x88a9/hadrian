"""Model persistence, venue CRUD and the system-delete RESTRICT guard (Phase 7)."""

from __future__ import annotations

import pytest

from app.models import LiveTrade

pytestmark = pytest.mark.integration


def test_live_trade_persists_full_shape(db_session, live_system, seed_live):
    lt = LiveTrade(
        system_id=live_system,
        asset="BTC",
        stage="closed",
        direction="long",
        entry_order_type="limit",
        planned_entry=110000,
        planned_stop=109950,
        actual_entry=110010,
        exit_price=110150,
        position_size_coins=0.02646,
        position_size_notional=2910.6,
        leverage=9.1,
        risk_usd=3.0,
        expected_loss=1.323,
        realized_pnl_usd=2.0,
        r_value=0.67,
        win_loss="win",
        deviation_pct=11.5,
        snap_entry_fee_pct=0.000144,
        snap_exit_fee_pct=0.000432,
    )
    db_session.add(lt)
    db_session.commit()
    db_session.refresh(lt)
    assert lt.id is not None
    assert lt.stage == "closed"
    assert lt.win_loss == "win"


def test_venue_crud_and_duplicate(client, seed_live):
    r = client.post("/venues", json={"name": "Hyperliquid", "notes": "perp dex"})
    assert r.status_code == 201
    vid = r.json()["id"]
    # duplicate name -> 409
    assert client.post("/venues", json={"name": "Hyperliquid"}).status_code == 409
    # rename
    r = client.patch(f"/venues/{vid}", json={"name": "HL"})
    assert r.status_code == 200
    assert r.json()["name"] == "HL"
    # list includes seeded CEX + HL
    names = {v["name"] for v in client.get("/venues").json()["items"]}
    assert {"CEX", "HL"} <= names


def test_system_delete_blocked_by_live_trade(client, seed_live, live_system, db_session):
    # without live trades: delete works
    from app.models import System

    spare = System(name="SPARE-H1-001", import_status="complete")
    db_session.add(spare)
    db_session.commit()
    assert client.delete(f"/systems/{spare.id}").status_code == 204

    # with a live trade: 409, system survives
    db_session.add(LiveTrade(system_id=live_system, stage="setup_sighted"))
    db_session.commit()
    r = client.delete(f"/systems/{live_system}")
    assert r.status_code == 409
    assert "live trade" in r.json()["detail"]


def test_create_unknown_system_404(client, seed_live):
    assert client.post("/live-trades", json={"system_id": 999999}).status_code == 404
