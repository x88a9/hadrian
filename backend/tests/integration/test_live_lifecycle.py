"""Ticket lifecycle: transitions, guards, close math, PATCH locks (Phase 7)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _new_ticket(client, system_id, **kw):
    body = {
        "system_id": system_id,
        "asset": "DEFAULT",
        "planned_entry": 110000,
        "planned_stop": 109950,
        "desired_risk_usd": 3.0,
    }
    body.update(kw)
    r = client.post("/live-trades", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _tr(client, tid, target, **kw):
    return client.post(
        f"/live-trades/{tid}/transition", json={"target_stage": target, **kw}
    )


def test_happy_path_all_stages(client, seed_live, live_system):
    t = _new_ticket(client, live_system)
    assert t["stage"] == "risk_calculated"  # run_risk_calc on create
    tid = t["id"]

    assert _tr(client, tid, "order_placed", entry_order_type="limit").json()["stage"] == "order_placed"
    j = _tr(client, tid, "entry_filled", actual_entry=110010).json()
    assert j["stage"] == "entry_filled"
    assert j["slippage"] == pytest.approx(10.0)
    assert _tr(client, tid, "running").json()["stage"] == "running"
    closed = _tr(client, tid, "closed", exit_price=110150).json()
    assert closed["stage"] == "closed"
    assert closed["realized_pnl_usd"] is not None
    assert closed["r_value"] is not None
    assert closed["win_loss"] == "win"
    assert closed["deviation_pct"] is not None
    assert closed["duration_seconds"] is not None
    assert closed["balance_after"] == pytest.approx(324.0 + closed["realized_pnl_usd"])

    # timestamps present + monotonic
    for f in ("setup_sighted_at", "risk_calculated_at", "order_placed_at",
              "entry_filled_at", "running_at", "closed_at"):
        assert closed[f] is not None


def test_illegal_transition_is_409(client, seed_live, live_system):
    t = _new_ticket(client, live_system, run_risk_calc=False)
    assert t["stage"] == "setup_sighted"
    # cannot jump straight to closed
    assert _tr(client, t["id"], "closed", exit_price=1).status_code == 409
    # cannot place order before risk calc
    assert _tr(client, t["id"], "order_placed").status_code == 409


def test_cancel_only_before_fill(client, seed_live, live_system):
    t = _new_ticket(client, live_system)
    tid = t["id"]
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=110000)
    # after fill, cancel is not allowed
    assert _tr(client, tid, "cancelled").status_code == 409


def test_cancel_from_setup(client, seed_live, live_system):
    t = _new_ticket(client, live_system, run_risk_calc=False)
    assert _tr(client, t["id"], "cancelled", note="verworfen").json()["stage"] == "cancelled"


def test_close_requires_exit_or_pnl(client, seed_live, live_system):
    t = _new_ticket(client, live_system)
    tid = t["id"]
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=110000)
    _tr(client, tid, "running")
    assert _tr(client, tid, "closed").status_code == 422


def test_close_with_explicit_pnl_overrides_price(client, seed_live, live_system):
    t = _new_ticket(client, live_system)
    tid = t["id"]
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=110000)
    _tr(client, tid, "running")
    # r = -3 / 3 = -1 -> loss
    closed = _tr(client, tid, "closed", realized_pnl_usd=-3.0).json()
    assert closed["realized_pnl_usd"] == pytest.approx(-3.0)
    assert closed["r_value"] == pytest.approx(-1.0)
    assert closed["win_loss"] == "loss"
    assert closed["balance_after"] == pytest.approx(321.0)


def test_short_close_pnl_sign(client, seed_live, live_system):
    t = _new_ticket(client, live_system, planned_entry=109000, planned_stop=109900)
    tid = t["id"]
    assert t["direction"] == "short"
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=109000)
    _tr(client, tid, "running")
    # short: price falls -> profit
    closed = _tr(client, tid, "closed", exit_price=108000).json()
    assert closed["realized_pnl_usd"] > 0


@pytest.mark.parametrize(
    "pnl,expected",
    [(0.15, "break_even"), (0.29, "break_even"), (0.45, "win"), (-0.45, "loss")],
)
def test_break_even_threshold(client, seed_live, live_system, pnl, expected):
    # risk_usd = 3.0, so |R| < 0.1 <=> |pnl| < 0.3
    t = _new_ticket(client, live_system)
    tid = t["id"]
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=110000)
    _tr(client, tid, "running")
    closed = _tr(client, tid, "closed", realized_pnl_usd=pnl).json()
    assert closed["win_loss"] == expected


def test_patch_notes_always_plan_locked_after_order(client, seed_live, live_system):
    t = _new_ticket(client, live_system)
    tid = t["id"]
    # notes editable in risk_calculated
    assert client.patch(f"/live-trades/{tid}", json={"notes": "hi"}).json()["notes"] == "hi"
    _tr(client, tid, "order_placed")
    # notes still editable
    assert client.patch(f"/live-trades/{tid}", json={"notes": "later"}).status_code == 200
    # plan field locked after order placed
    assert client.patch(f"/live-trades/{tid}", json={"planned_entry": 5}).status_code == 409


def test_delete_rules(client, seed_live, live_system):
    """Every stage is deletable — wrongly recorded trades have to be removable;
    der Kontostand-Beitrag wird dabei rückabgewickelt — siehe
    ``test_balance_reversal.py``."""
    t = _new_ticket(client, live_system, run_risk_calc=False)  # setup_sighted
    assert client.delete(f"/live-trades/{t['id']}").status_code == 204
    t2 = _new_ticket(client, live_system)  # risk_calculated
    assert client.delete(f"/live-trades/{t2['id']}").status_code == 204
    assert client.delete(f"/live-trades/{t2['id']}").status_code == 404
