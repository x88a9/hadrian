"""Account balance ledger + live-only metrics aggregation (Phase 7)."""

from __future__ import annotations

import pytest

from app.models import LiveTrade, Trade

pytestmark = pytest.mark.integration


def _run_to_close(client, system_id, pnl):
    t = client.post(
        "/live-trades",
        json={
            "system_id": system_id,
            "asset": "DEFAULT",
            "planned_entry": 110000,
            "planned_stop": 109950,
            "desired_risk_usd": 3.0,
        },
    ).json()
    tid = t["id"]
    client.post(f"/live-trades/{tid}/transition", json={"target_stage": "order_placed"})
    client.post(
        f"/live-trades/{tid}/transition",
        json={"target_stage": "entry_filled", "actual_entry": 110000},
    )
    client.post(f"/live-trades/{tid}/transition", json={"target_stage": "running"})
    return client.post(
        f"/live-trades/{tid}/transition",
        json={"target_stage": "closed", "realized_pnl_usd": pnl},
    ).json()


def test_balance_forward_and_correction(client, seed_live, live_system):
    assert client.get("/account/balance").json()["current_balance"] == pytest.approx(324.0)

    _run_to_close(client, live_system, 12.5)
    assert client.get("/account/balance").json()["current_balance"] == pytest.approx(336.5)

    # manual correction to an absolute value
    client.post("/account/balance", json={"balance": 300.0, "note": "sync"})
    bal = client.get("/account/balance").json()
    assert bal["current_balance"] == pytest.approx(300.0)
    # the correction row records the delta
    corr = bal["history"][0]
    assert corr["change_type"] == "manual"
    assert corr["delta"] == pytest.approx(300.0 - 336.5)

    # the next risk calc uses the corrected balance
    j = client.post(
        "/risk/calc",
        json={"entry_price": 110000, "stop_price": 109950, "risk_pct": 1.0},
    ).json()
    assert j["portfolio_size"] == pytest.approx(300.0)


def test_metrics_exclude_cancelled_open_and_backtest(
    client, seed_live, live_system, db_session
):
    # 2 closed (a win, a loss)
    _run_to_close(client, live_system, 6.0)   # win
    _run_to_close(client, live_system, -3.0)  # loss
    # 1 cancelled
    cancelled = client.post(
        "/live-trades",
        json={"system_id": live_system, "asset": "DEFAULT", "run_risk_calc": False},
    ).json()
    client.post(
        f"/live-trades/{cancelled['id']}/transition",
        json={"target_stage": "cancelled"},
    )
    # 1 running (open)
    _open = client.post(
        "/live-trades",
        json={
            "system_id": live_system,
            "asset": "DEFAULT",
            "planned_entry": 110000,
            "planned_stop": 109950,
            "desired_risk_usd": 3.0,
        },
    ).json()
    client.post(f"/live-trades/{_open['id']}/transition", json={"target_stage": "order_placed"})
    client.post(
        f"/live-trades/{_open['id']}/transition",
        json={"target_stage": "entry_filled", "actual_entry": 110000},
    )
    # a backtest trade on the same system (must not leak into live metrics)
    db_session.add(Trade(system_id=live_system, r_value=99.0, win_loss="win", source="manual"))
    db_session.commit()

    m = client.get("/live-trades/metrics").json()
    assert m["closed_count"] == 2
    assert m["open_count"] == 1
    assert m["wins"] == 1
    assert m["losses"] == 1
    assert m["win_rate"] == pytest.approx(0.5)
    assert m["total_pnl_usd"] == pytest.approx(3.0)  # 6 - 3
    # total_r = 6/3 + (-3/3) = 2 - 1 = 1
    assert m["total_r"] == pytest.approx(1.0)
    assert m["current_balance"] == pytest.approx(324.0 + 3.0)

    # system_id scope: same numbers for the only system, empty for another
    scoped = client.get("/live-trades/metrics", params={"system_id": live_system}).json()
    assert scoped["closed_count"] == 2
    other = client.get("/live-trades/metrics", params={"system_id": 987654}).json()
    assert other["closed_count"] == 0 and other["open_count"] == 0
