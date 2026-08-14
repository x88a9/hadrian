"""Fee-snapshot isolation — the hard Phase-7 requirement.

Create a ticket, change fees globally (a new asset-settings version), and assert
the old ticket is untouched: its snapshot fees and its computed position size
stay identical, and a recompute of the old ticket still uses the OLD fees. A new
ticket picks up the NEW fees.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _create(client, system_id, **kw):
    body = {
        "system_id": system_id,
        "asset": "DEFAULT",
        "planned_entry": 109000,
        "planned_stop": 109900,
        "desired_risk_usd": 3.0,
    }
    body.update(kw)
    r = client.post("/live-trades", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_fee_change_never_touches_existing_trade(client, seed_live, live_system):
    old = _create(client, live_system)
    old_snap = old["snap_entry_fee_pct"]
    old_coins = old["position_size_coins"]
    assert old_snap == pytest.approx(0.000144)
    assert old_coins == pytest.approx(0.00312, abs=1e-8)

    # Global fee change: new version with 10x the entry fee.
    r = client.post(
        f"/venues/{seed_live['venue_id']}/asset-settings",
        json={
            "asset": "DEFAULT",
            "entry_fee_pct": 0.00144,
            "exit_fee_pct": 0.00432,
            "min_position_size": 0.00001,
        },
    )
    assert r.status_code == 201

    # (a) old trade unchanged
    fetched = client.get(f"/live-trades/{old['id']}").json()
    assert fetched["snap_entry_fee_pct"] == pytest.approx(0.000144)
    assert fetched["position_size_coins"] == pytest.approx(old_coins, abs=1e-12)

    # (b) recompute of the old trade still uses the old (snapshot) fees
    rc = client.post(
        f"/live-trades/{old['id']}/transition",
        json={"target_stage": "risk_calculated"},
    ).json()
    assert rc["position_size_coins"] == pytest.approx(old_coins, abs=1e-12)
    assert rc["snap_entry_fee_pct"] == pytest.approx(0.000144)

    # (c) a new trade picks up the new fees
    new = _create(client, live_system)
    assert new["snap_entry_fee_pct"] == pytest.approx(0.00144)
    assert new["position_size_coins"] != pytest.approx(old_coins, abs=1e-8)

    # (d) current settings = newest version; full history is retained
    current = client.get(
        "/asset-settings", params={"venue_id": seed_live["venue_id"], "current": True}
    ).json()
    assert current[0]["entry_fee_pct"] == pytest.approx(0.00144)
    # Historie je Asset: DEFAULT hat jetzt zwei Versionen (alt + neu).
    history = client.get(
        "/asset-settings",
        params={"venue_id": seed_live["venue_id"], "asset": "DEFAULT"},
    ).json()
    assert len(history) == 2
    assert history[0]["entry_fee_pct"] == pytest.approx(0.00144)  # neueste zuerst
    assert history[1]["entry_fee_pct"] == pytest.approx(0.000144)
