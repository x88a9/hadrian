"""Nachträgliche Korrektur von Ausführungsfeldern + freier Trade (Phase 8).

Anlass aus dem Realbetrieb: ein vertippter ``actual_entry`` (109000108990) war
nach dem Fill dauerhaft unveränderbar. Ausführungs- und Ergebnisfelder müssen
korrigierbar sein — mit denselben Ableitungen wie beim Schließen.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

START = 324.0
COINS = 0.02646  # long 110000/109950, risk 3.00 (verified reference case)


def _new_ticket(client, system_id=None, **kw):
    body = {
        "asset": "DEFAULT",
        "planned_entry": 110000,
        "planned_stop": 109950,
        "desired_risk_usd": 3.0,
    }
    if system_id is not None:
        body["system_id"] = system_id
    body.update(kw)
    return client.post("/live-trades", json=body)


def _tr(client, tid, target, **kw):
    r = client.post(
        f"/live-trades/{tid}/transition", json={"target_stage": target, **kw}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _filled(client, system_id, actual_entry=110000):
    t = _new_ticket(client, system_id).json()
    tid = t["id"]
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=actual_entry)
    return tid


def _closed(client, system_id, **close_kw):
    tid = _filled(client, system_id)
    _tr(client, tid, "running")
    return _tr(client, tid, "closed", **close_kw)


def _balance(client) -> float:
    return client.get("/account/balance").json()["current_balance"]


# --------------------------------------------------------------------------- #
# Aufgabe 2: Ausführungsfelder korrigierbar
# --------------------------------------------------------------------------- #
def test_fix_typo_in_actual_entry_after_fill(client, seed_live, live_system):
    tid = _filled(client, system_id=live_system, actual_entry=109000108990)
    r = client.patch(f"/live-trades/{tid}", json={"actual_entry": 110010})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["actual_entry"] == pytest.approx(110010)
    # Slippage zieht mit.
    assert j["slippage"] == pytest.approx(10.0)


def test_actual_stop_editable_while_running(client, seed_live, live_system):
    tid = _filled(client, live_system)
    _tr(client, tid, "running")
    r = client.patch(f"/live-trades/{tid}", json={"actual_stop": 109960})
    assert r.status_code == 200, r.text
    assert r.json()["actual_stop"] == pytest.approx(109960)


def test_actual_entry_locked_before_fill(client, seed_live, live_system):
    t = _new_ticket(client, live_system, run_risk_calc=False).json()
    assert t["stage"] == "setup_sighted"
    r = client.patch(f"/live-trades/{t['id']}", json={"actual_entry": 110010})
    assert r.status_code == 409, r.text


def test_result_fields_locked_before_close(client, seed_live, live_system):
    tid = _filled(client, live_system)
    _tr(client, tid, "running")
    for field, value in (
        ("exit_price", 110100),
        ("realized_pnl_usd", 5.0),
        ("fees_paid", 0.5),
        ("funding_paid", 0.1),
    ):
        r = client.patch(f"/live-trades/{tid}", json={field: value})
        assert r.status_code == 409, f"{field}: {r.text}"


def test_patch_exit_price_rederives_everything(client, seed_live, live_system):
    closed = _closed(client, live_system, exit_price=110150)
    assert closed["win_loss"] == "win"

    r = client.patch(f"/live-trades/{closed['id']}", json={"exit_price": 109900})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["exit_price"] == pytest.approx(109900)
    assert j["realized_pnl_usd"] < 0
    assert j["r_value"] == pytest.approx(j["realized_pnl_usd"] / 3.0)
    assert j["win_loss"] == "loss"
    assert j["deviation_pct"] is not None
    # Saldo trägt genau EINEN Beitrag dieses Trades.
    assert _balance(client) == pytest.approx(
        START + j["realized_pnl_usd"], abs=1e-9
    )


def test_patch_fees_recomputes_net_result(client, seed_live, live_system):
    closed = _closed(client, live_system, exit_price=110150)
    assert closed["fees_paid"] > 0

    r = client.patch(f"/live-trades/{closed['id']}", json={"fees_paid": 0.0})
    assert r.status_code == 200, r.text
    j = r.json()
    # Ohne Fees/Funding ist realized = brutto = coins * (exit - entry).
    assert j["realized_pnl_usd"] == pytest.approx(COINS * 150.0, abs=1e-9)
    assert _balance(client) == pytest.approx(
        START + j["realized_pnl_usd"], abs=1e-9
    )


def test_patch_actual_entry_on_closed_trade(client, seed_live, live_system):
    closed = _closed(client, live_system, exit_price=110150)
    old = closed["realized_pnl_usd"]

    r = client.patch(f"/live-trades/{closed['id']}", json={"actual_entry": 110050})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["slippage"] == pytest.approx(50.0)
    # Schlechterer Einstieg -> kleineres Ergebnis, Saldo bleibt konsistent.
    assert j["realized_pnl_usd"] < old
    assert _balance(client) == pytest.approx(
        START + j["realized_pnl_usd"], abs=1e-9
    )


def test_plan_fields_still_locked_after_order(client, seed_live, live_system):
    tid = _filled(client, live_system)
    assert client.patch(
        f"/live-trades/{tid}", json={"planned_entry": 5}
    ).status_code == 409
    # notes bleiben immer frei
    assert client.patch(
        f"/live-trades/{tid}", json={"notes": "ok"}
    ).status_code == 200


# --------------------------------------------------------------------------- #
# Aufgabe 3: freier Trade ohne System
# --------------------------------------------------------------------------- #
def test_create_free_trade_without_system(client, seed_live):
    r = _new_ticket(client, system_id=None)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["system_id"] is None
    assert j["system_name"] is None
    assert j["asset"] == "DEFAULT"
    # Rechner lief trotzdem (Snapshot + Sizing hängen nicht am System).
    assert j["stage"] == "risk_calculated"
    assert j["position_size_coins"] == pytest.approx(COINS)

    listed = client.get("/live-trades").json()
    assert [i["id"] for i in listed["items"]] == [j["id"]]


def test_free_trade_counts_in_live_metrics(client, seed_live):
    tid = _new_ticket(client, system_id=None).json()["id"]
    _tr(client, tid, "order_placed")
    _tr(client, tid, "entry_filled", actual_entry=110000)
    _tr(client, tid, "running")
    _tr(client, tid, "closed", realized_pnl_usd=6.0)

    m = client.get("/live-trades/metrics").json()
    assert m["closed_count"] == 1
    assert m["wins"] == 1
    assert m["total_pnl_usd"] == pytest.approx(6.0)
    assert m["total_r"] == pytest.approx(2.0)
    assert m["current_balance"] == pytest.approx(START + 6.0)


def test_unknown_system_still_404(client, seed_live):
    assert _new_ticket(client, system_id=999999).status_code == 404
