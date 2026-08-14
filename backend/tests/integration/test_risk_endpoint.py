"""The standalone risk endpoint reproduces the verified reference cases."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_long_case_via_seeded_settings(client, seed_live):
    r = client.post(
        "/risk/calc",
        json={"entry_price": 110000, "stop_price": 109950, "desired_risk_usd": 3.0},
    )
    assert r.status_code == 200
    j = r.json()
    # portfolio defaults to the seeded balance (324.00)
    assert j["portfolio_size"] == pytest.approx(324.0)
    assert j["adjusted_pos_size"] == pytest.approx(0.02646, abs=1e-8)
    assert j["adjusted_notional"] == pytest.approx(2910.60, abs=1e-8)
    assert j["adjusted_fees"] == pytest.approx(1.6765056, abs=1e-8)
    assert j["adjusted_risk"] == pytest.approx(2.9995056, abs=1e-8)
    assert j["valid_risk"] is True
    assert j["direction"] == "long"
    assert j["leverage"] == pytest.approx(9.1, abs=1e-9)


def test_short_case_via_seeded_settings(client, seed_live):
    r = client.post(
        "/risk/calc",
        json={"entry_price": 109000, "stop_price": 109900, "desired_risk_usd": 3.0},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["adjusted_pos_size"] == pytest.approx(0.00312, abs=1e-8)
    assert j["adjusted_notional"] == pytest.approx(340.08, abs=1e-8)
    assert j["adjusted_risk"] == pytest.approx(3.00388608, abs=1e-8)
    assert j["valid_risk"] is True
    assert j["direction"] == "short"
    assert j["leverage"] == pytest.approx(1.2, abs=1e-9)


def test_risk_pct_derives_desired_from_portfolio(client, seed_live):
    # 3.0 / 324 * 100 = 0.9259...% -> desired 3.0
    r = client.post(
        "/risk/calc",
        json={
            "entry_price": 110000,
            "stop_price": 109950,
            "risk_pct": 3.0 / 324 * 100,
        },
    )
    assert r.status_code == 200
    assert r.json()["adjusted_pos_size"] == pytest.approx(0.02646, abs=1e-8)


def test_requires_exactly_one_risk_input(client, seed_live):
    r = client.post(
        "/risk/calc",
        json={"entry_price": 110000, "stop_price": 109950},
    )
    assert r.status_code == 422
