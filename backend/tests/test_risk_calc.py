"""Verified risk-calculator tests.

The two reference cases are fixed inputs with hand-checked expected outputs.
They MUST reproduce to ~1e-8 — if they do not, the calculator is wrong, not the
reference. See docs/DECISIONS.md, "Position sizing rounds, it does not floor".
"""

from __future__ import annotations

import math

import pytest

from app.services.risk_calc import RiskInputs, compute_risk, deviation_pct

ENTRY_FEE = 0.000144  # 0.0144 %
EXIT_FEE = 0.000432  # 0.0432 %
MIN_SIZE = 0.00001
PORTFOLIO = 324.00
RISK = 3.00

TOL = 1e-8


def _inp(entry: float, stop: float, *, desired_risk: float = RISK, **kw) -> RiskInputs:
    """RiskInputs with the reference defaults; every field overridable by keyword."""
    fields = {
        "entry_price": entry,
        "stop_price": stop,
        "desired_risk_usd": desired_risk,
        "portfolio_size": PORTFOLIO,
        "entry_fee_pct": ENTRY_FEE,
        "exit_fee_pct": EXIT_FEE,
        "min_position_size": MIN_SIZE,
    }
    fields.update(kw)
    return RiskInputs(**fields)


def test_long_reference_case():
    r = compute_risk(_inp(110000, 109950))
    assert math.isclose(r.initial_pos_size, 0.02646436133, abs_tol=1e-8)
    assert math.isclose(r.adjusted_pos_size, 0.02646, abs_tol=TOL)
    assert math.isclose(r.adjusted_notional, 2910.60, abs_tol=TOL)
    assert math.isclose(r.adjusted_fees, 1.6765056, abs_tol=TOL)
    assert math.isclose(r.adjusted_risk, 2.9995056, abs_tol=TOL)
    assert r.valid_risk is True
    assert r.direction == "long"
    assert math.isclose(r.leverage, 9.1, abs_tol=1e-9)


def test_short_reference_case():
    r = compute_risk(_inp(109000, 109900))
    assert math.isclose(r.initial_pos_size, 0.003115963705, abs_tol=1e-8)
    # ROUND (not floor): 311.596 -> 312, so 0.00312 (floor would give 0.00311).
    assert math.isclose(r.adjusted_pos_size, 0.00312, abs_tol=TOL)
    assert math.isclose(r.adjusted_notional, 340.08, abs_tol=TOL)
    assert math.isclose(r.adjusted_risk, 3.00388608, abs_tol=TOL)
    assert r.valid_risk is True
    assert r.direction == "short"
    assert math.isclose(r.leverage, 1.2, abs_tol=1e-9)


def test_round_not_floor_is_the_difference():
    """Guard against a regression to floor(): floor would yield 0.00311."""
    r = compute_risk(_inp(109000, 109900))
    assert r.adjusted_pos_size != pytest.approx(0.00311, abs=1e-9)


def test_risk_modifier_scales_desired_risk():
    full = compute_risk(_inp(110000, 109950))
    half = compute_risk(_inp(110000, 109950, risk_modifier=0.5))
    assert math.isclose(half.effective_desired_risk, full.effective_desired_risk / 2)
    # Half the desired risk -> roughly half the position size.
    assert half.adjusted_pos_size < full.adjusted_pos_size


def test_direction_derived_from_stop_side():
    assert compute_risk(_inp(100, 90)).direction == "long"  # stop below entry
    assert compute_risk(_inp(100, 110)).direction == "short"  # stop above entry


def test_deviation_pct():
    assert deviation_pct(1.1, 1.0) == pytest.approx(10.0)
    assert deviation_pct(0.9, 1.0) == pytest.approx(10.0)
    assert deviation_pct(1.0, 0.0) is None


# --- Phase 7.1: asset-spezifische Lot-Size + Leverage-Trennung --------------- #


def test_leverage_split_long_and_short():
    """Implied (a ratio) / required incl. buffer / settable (integer only)."""
    long = compute_risk(_inp(110000, 109950, max_leverage=40, leverage_step=1.0))
    assert math.isclose(long.implicit_leverage, 2910.60 / 324.0, abs_tol=1e-9)
    assert math.isclose(long.leverage, 9.1, abs_tol=1e-9)  # reference unchanged
    assert long.exchange_leverage == pytest.approx(10.0)  # ganzzahlig aufgerundet
    assert long.leverage_exceeds_max is False

    short = compute_risk(_inp(109000, 109900, max_leverage=40, leverage_step=1.0))
    assert math.isclose(short.implicit_leverage, 340.08 / 324.0, abs_tol=1e-9)
    assert math.isclose(short.leverage, 1.2, abs_tol=1e-9)
    assert short.exchange_leverage == pytest.approx(2.0)


def test_leverage_exceeds_asset_max_is_flagged():
    # XMR really only allows 5x, so a 9.1x position has to be flagged.
    r = compute_risk(_inp(110000, 109950, max_leverage=5, leverage_step=1.0))
    assert r.exchange_leverage == pytest.approx(10.0)
    assert r.leverage_exceeds_max is True


def test_asset_lot_size_is_respected():
    """DOT trades in steps of 0.1, so the size has to snap to that grid."""
    r = compute_risk(_inp(4.0, 3.5, min_position_size=0.1))
    assert r.adjusted_pos_size == pytest.approx(6.0, abs=1e-9)
    assert r.min_position_size == pytest.approx(0.1)
    # without the lot-size correction this would be 5.97248 -> unplaceable
    assert r.adjusted_pos_size != pytest.approx(5.97248, abs=1e-6)


def test_coarse_lot_size_pushing_risk_over_tolerance_is_invalid():
    """The most dangerous case: rounding pushes risk beyond the tolerance.

    Muss valid_risk=False liefern UND das tatsächliche Risiko ausweisen, statt
    still eine zu große Position vorzuschlagen.
    """
    r = compute_risk(_inp(4.0, 0.5, min_position_size=0.1))
    assert r.adjusted_pos_size == pytest.approx(0.9, abs=1e-9)
    assert r.adjusted_risk > r.risk_upper_bound
    assert r.valid_risk is False
    assert r.risk_overshoot_pct > 5.0
    # The safe alternative one step lower is returned alongside.
    assert r.floor_pos_size == pytest.approx(0.8, abs=1e-9)
    assert r.floor_risk < r.adjusted_risk


def test_position_rounding_to_zero_is_invalid():
    r = compute_risk(_inp(4.0, 0.1, desired_risk=0.05, min_position_size=1.0))
    assert r.adjusted_pos_size == 0.0
    assert r.rounds_to_zero is True
    assert r.valid_risk is False


def test_below_min_order_value_is_flagged():
    # A notional of 340.08 clears a 10 USDC minimum but not a 1000 USDC one.
    ok = compute_risk(_inp(109000, 109900, min_order_value_usd=10.0))
    assert ok.below_min_order_value is False
    too_small = compute_risk(_inp(109000, 109900, min_order_value_usd=1000.0))
    assert too_small.below_min_order_value is True
