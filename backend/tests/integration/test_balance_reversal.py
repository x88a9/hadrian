"""Balance reversal when a trade is deleted or corrected.

Kernforderung: der Ledger bleibt append-only (Audit-Trail), aber der Saldo darf
nach dem Löschen eines Trades KEINE Spur mehr von ihm tragen — sonst verfälscht
ein falsch erfasster Trade den Kontostand dauerhaft.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

START = 324.0


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
    r = client.post(
        f"/live-trades/{tid}/transition", json={"target_stage": target, **kw}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _close(client, system_id, **close_kw):
    """Ticket durch alle Stufen bis 'closed' fahren."""
    t = _new_ticket(client, system_id)
    tid = t["id"]
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=110000)
    _tr(client, tid, "running")
    return _tr(client, tid, "closed", **close_kw)


def _balance(client) -> float:
    return client.get("/account/balance").json()["current_balance"]


def test_delete_closed_trade_restores_balance_exactly(client, seed_live, live_system):
    assert _balance(client) == pytest.approx(START)

    closed = _close(client, live_system, exit_price=110150)
    assert closed["realized_pnl_usd"] != 0
    assert _balance(client) != pytest.approx(START, abs=1e-9)

    assert client.delete(f"/live-trades/{closed['id']}").status_code == 204
    assert _balance(client) == pytest.approx(START, abs=1e-9)


def test_delete_leaves_audit_row_with_trade_id(client, seed_live, live_system):
    closed = _close(client, live_system, exit_price=110150)
    tid = closed["id"]
    client.delete(f"/live-trades/{tid}")

    hist = client.get("/account/balance").json()["history"]
    # Ledger schreibt nur fort: Startzeile + Abschluss + Rückabwicklung.
    assert len(hist) == 3
    rev = [h for h in hist if h["change_type"] == "trade_delete"]
    assert len(rev) == 1
    assert rev[0]["delta"] == pytest.approx(-closed["realized_pnl_usd"])
    # The FK is ON DELETE SET NULL, so the reference is gone and the trade ID
    # has to live in the note text.
    assert rev[0]["live_trade_id"] is None
    assert f"#{tid}" in (rev[0]["note"] or "")


def test_delete_one_of_two_keeps_the_other(client, seed_live, live_system):
    first = _close(client, live_system, exit_price=110150)
    second = _close(client, live_system, exit_price=110300)
    assert _balance(client) == pytest.approx(
        START + first["realized_pnl_usd"] + second["realized_pnl_usd"], abs=1e-9
    )

    assert client.delete(f"/live-trades/{first['id']}").status_code == 204
    assert _balance(client) == pytest.approx(
        START + second["realized_pnl_usd"], abs=1e-9
    )


def test_delete_pnl_closed_trade_restores_balance(client, seed_live, live_system):
    """The 'close with an explicit realized_pnl_usd' path is reversible too."""
    closed = _close(client, live_system, realized_pnl_usd=-7.25)
    assert closed["realized_pnl_usd"] == pytest.approx(-7.25)
    assert _balance(client) == pytest.approx(START - 7.25, abs=1e-9)

    assert client.delete(f"/live-trades/{closed['id']}").status_code == 204
    assert _balance(client) == pytest.approx(START, abs=1e-9)


@pytest.mark.parametrize(
    "stage", ["setup_sighted", "risk_calculated", "order_placed", "entry_filled",
              "running", "cancelled"]
)
def test_delete_allowed_in_every_stage(client, seed_live, live_system, stage):
    t = _new_ticket(client, live_system, run_risk_calc=(stage != "setup_sighted"))
    tid = t["id"]
    if stage in ("order_placed", "entry_filled", "running"):
        _tr(client, tid, "order_placed")
    if stage in ("entry_filled", "running"):
        _tr(client, tid, "entry_filled", actual_entry=110000)
    if stage == "running":
        _tr(client, tid, "running")
    if stage == "cancelled":
        _tr(client, tid, "cancelled")

    assert client.get(f"/live-trades/{tid}").json()["stage"] == stage
    assert client.delete(f"/live-trades/{tid}").status_code == 204
    assert client.get(f"/live-trades/{tid}").status_code == 404
    # Offene/abgebrochene Tickets haben nichts gebucht -> Saldo unverändert.
    assert _balance(client) == pytest.approx(START, abs=1e-9)


def test_correction_does_not_double_count(client, seed_live, live_system):
    """PATCH to a different exit_price -> balance = start + the NEW realized."""
    closed = _close(client, live_system, exit_price=110150)
    old_realized = closed["realized_pnl_usd"]
    assert _balance(client) == pytest.approx(START + old_realized, abs=1e-9)

    r = client.patch(f"/live-trades/{closed['id']}", json={"exit_price": 110300})
    assert r.status_code == 200, r.text
    corrected = r.json()
    assert corrected["realized_pnl_usd"] != pytest.approx(old_realized)
    assert _balance(client) == pytest.approx(
        START + corrected["realized_pnl_usd"], abs=1e-9
    )
    assert corrected["balance_after"] == pytest.approx(
        START + corrected["realized_pnl_usd"], abs=1e-9
    )


def test_delete_after_correction_restores_balance(client, seed_live, live_system):
    closed = _close(client, live_system, exit_price=110150)
    client.patch(f"/live-trades/{closed['id']}", json={"exit_price": 109800})
    assert client.delete(f"/live-trades/{closed['id']}").status_code == 204
    assert _balance(client) == pytest.approx(START, abs=1e-9)


def test_correction_of_pnl_closed_trade(client, seed_live, live_system):
    closed = _close(client, live_system, realized_pnl_usd=-3.0)
    r = client.patch(
        f"/live-trades/{closed['id']}", json={"realized_pnl_usd": 4.5}
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["realized_pnl_usd"] == pytest.approx(4.5)
    assert j["r_value"] == pytest.approx(1.5)
    assert j["win_loss"] == "win"
    assert _balance(client) == pytest.approx(START + 4.5, abs=1e-9)
