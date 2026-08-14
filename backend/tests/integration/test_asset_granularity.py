"""Asset-spezifische Lot-Size + Asset-Bindung ans System (Phase 7.1).

Der zentrale Fehler, den diese Tests verhindern: für ein Nicht-BTC-Asset mit
BTCs Schrittweite zu rechnen und damit eine nicht platzierbare (oder zu große)
Position vorzuschlagen.
"""

from __future__ import annotations

import pytest

from app.models import System

pytestmark = pytest.mark.integration


def test_risk_calc_uses_asset_lot_size(client, seed_live):
    """DOT snaps to 0.1 and BTC to 0.00001, given the identical setup."""
    dot = client.post(
        "/risk/calc",
        json={
            "entry_price": 4.0,
            "stop_price": 3.5,
            "desired_risk_usd": 3.0,
            "asset": "DOT",
        },
    ).json()
    assert dot["min_position_size"] == pytest.approx(0.1)
    assert dot["adjusted_pos_size"] == pytest.approx(6.0, abs=1e-9)
    assert dot["settings_fallback"] is False
    assert dot["max_leverage"] == pytest.approx(10.0)

    btc = client.post(
        "/risk/calc",
        json={
            "entry_price": 4.0,
            "stop_price": 3.5,
            "desired_risk_usd": 3.0,
            "asset": "BTC",
        },
    ).json()
    assert btc["min_position_size"] == pytest.approx(0.00001)
    # feinere Schrittweite -> andere (feinere) Größe als DOT
    assert btc["adjusted_pos_size"] != pytest.approx(6.0, abs=1e-6)


def test_unknown_asset_is_flagged_as_fallback(client, seed_live):
    """Ein unbekanntes Asset darf NICHT still mit BTC-Granularität rechnen."""
    r = client.post(
        "/risk/calc",
        json={
            "entry_price": 4.0,
            "stop_price": 3.5,
            "desired_risk_usd": 3.0,
            "asset": "NOPE",
        },
    ).json()
    assert r["settings_fallback"] is True
    assert r["settings_asset"] == "DEFAULT"


def test_coarse_lot_size_invalidates_risk_via_api(client, seed_live):
    """Rounding beyond tolerance -> valid_risk False plus the actual risk."""
    r = client.post(
        "/risk/calc",
        json={
            "entry_price": 4.0,
            "stop_price": 0.5,
            "desired_risk_usd": 3.0,
            "asset": "DOT",
        },
    ).json()
    assert r["valid_risk"] is False
    assert r["adjusted_risk"] > r["risk_upper_bound"]
    assert r["risk_overshoot_pct"] > 5.0
    assert r["floor_pos_size"] == pytest.approx(0.8, abs=1e-9)


def test_leverage_split_exposed_via_api(client, seed_live):
    r = client.post(
        "/risk/calc",
        json={
            "entry_price": 110000,
            "stop_price": 109950,
            "desired_risk_usd": 3.0,
            "asset": "BTC",
        },
    ).json()
    assert r["implicit_leverage"] == pytest.approx(2910.60 / 324.0, abs=1e-9)
    assert r["leverage"] == pytest.approx(9.1, abs=1e-9)
    assert r["exchange_leverage"] == pytest.approx(10.0)  # integer-only venue
    assert r["leverage_exceeds_max"] is False


def test_live_trade_inherits_asset_from_system(client, seed_live, db_session):
    """System carries the asset -> the live trade inherits it and its lot size."""
    sys_dot = System(name="MR-H1-900", import_status="complete", asset="DOT")
    db_session.add(sys_dot)
    db_session.commit()

    created = client.post(
        "/live-trades",
        json={
            "system_id": sys_dot.id,
            "planned_entry": 4.0,
            "planned_stop": 3.5,
            "desired_risk_usd": 3.0,
        },
    ).json()
    assert created["asset"] == "DOT"  # ohne dass es mitgegeben wurde
    assert created["snap_min_position_size"] == pytest.approx(0.1)
    assert created["position_size_coins"] == pytest.approx(6.0, abs=1e-9)
    assert created["snap_max_leverage"] == pytest.approx(10.0)
    assert created["exchange_leverage"] is not None


def test_explicit_asset_overrides_system_asset(client, seed_live, db_session):
    sys_dot = System(name="MR-H1-901", import_status="complete", asset="DOT")
    db_session.add(sys_dot)
    db_session.commit()
    created = client.post(
        "/live-trades",
        json={
            "system_id": sys_dot.id,
            "asset": "SOL",
            "planned_entry": 200.0,
            "planned_stop": 190.0,
            "desired_risk_usd": 3.0,
        },
    ).json()
    assert created["asset"] == "SOL"
    assert created["snap_min_position_size"] == pytest.approx(0.01)


def test_system_asset_is_patchable_and_override_tracked(client, seed_live, db_session):
    s = System(name="B-H1-902", import_status="complete")
    db_session.add(s)
    db_session.commit()
    r = client.patch(f"/systems/{s.id}", json={"asset": "XMR"})
    assert r.status_code == 200
    body = r.json()
    assert body["asset"] == "XMR"
    # asset is protected against re-import via user_overrides
    assert "asset" in body["user_overrides"]
