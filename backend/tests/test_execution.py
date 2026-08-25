"""Sizing, order construction and the two execution modes.

Nothing here touches a network. The testnet executor is exercised through
``httpx.MockTransport``, which covers everything about it except the signature
— that needs a funded testnet wallet and is the operator's acceptance test, not
this suite's. See the module docstring of ``app/execution/testnet.py``.
"""

from __future__ import annotations

import httpx
import pytest

from app.execution.dry_run import DryRunExecutor
from app.execution.mode import ExecutionMode, MainnetDisabled
from app.execution.orders import OrderIntent, OrderRejected, build_executor
from app.execution.sizing import (
    STAGE_RISK_SCALE,
    StageNotTradeable,
    size_for_stage,
)
from app.execution import testnet as testnet_module
from app.execution.testnet import TestnetNotConfigured as NotConfigured

# The hand-checked reference case from docs/DECISIONS.md, which the risk
# calculator reproduces to ~1e-8 and which this phase must not disturb.
REFERENCE = dict(
    entry_price=109000.0,
    stop_price=109900.0,
    desired_risk_usd=3.0,
    portfolio_size=324.0,
)


def intent(**overrides) -> OrderIntent:
    kwargs = dict(
        asset="BTC",
        direction="long",
        size=0.00312,
        reference_price=109000.0,
        stop_price=109900.0,
    )
    kwargs.update(overrides)
    return OrderIntent(**kwargs)


# --------------------------------------------------------------------------- #
# Stage-scaled sizing
# --------------------------------------------------------------------------- #


def test_an_active_system_reproduces_the_verified_reference_case():
    """Stage scaling must not disturb the numbers the calculator was verified
    against. At full scale the answer has to be exactly the old one."""
    sized = size_for_stage(None, stage="active", **REFERENCE)

    assert sized.stage_scale == 1.0
    assert sized.risk.adjusted_pos_size == 0.00312
    assert sized.risk.adjusted_notional == 340.08
    assert sized.risk.adjusted_risk == pytest.approx(3.00388608, abs=1e-9)


def test_live_testing_takes_a_quarter_of_the_risk():
    full = size_for_stage(None, stage="active", **REFERENCE)
    testing = size_for_stage(None, stage="live_testing", **REFERENCE)

    assert testing.stage_scale == 0.25
    assert testing.size < full.size
    assert testing.risk.adjusted_risk == pytest.approx(full.risk.adjusted_risk / 4, rel=0.02)


def test_a_backtest_system_cannot_be_sized_at_all():
    """It raises rather than returning a zero-size order, which a caller could
    easily go on to send."""
    with pytest.raises(StageNotTradeable, match="does not trade live"):
        size_for_stage(None, stage="backtest", **REFERENCE)


def test_a_retired_system_cannot_be_sized_either():
    with pytest.raises(StageNotTradeable):
        size_for_stage(None, stage="retired", **REFERENCE)


def test_an_unknown_stage_is_refused_rather_than_defaulted():
    with pytest.raises(StageNotTradeable, match="unknown system stage"):
        size_for_stage(None, stage="probably_fine", **REFERENCE)


def test_every_system_status_has_a_declared_scale():
    """A status the sizing code has never heard of would otherwise surface as a
    runtime refusal the first time that system tried to trade."""
    from app.models.system import SYSTEM_STATUSES

    assert set(SYSTEM_STATUSES) == set(STAGE_RISK_SCALE)


def test_a_position_that_rounds_to_zero_is_reported_not_sent():
    sized = size_for_stage(
        None,
        stage="active",
        entry_price=109000.0,
        stop_price=109900.0,
        desired_risk_usd=0.0001,
        portfolio_size=324.0,
    )
    assert not sized.tradeable
    assert "rounds to zero" in sized.rejection_reason()


# --------------------------------------------------------------------------- #
# Order construction
# --------------------------------------------------------------------------- #


def test_a_long_limit_crosses_upward_and_a_short_downward():
    """The order should cross the spread, not rest on the book: a resting order
    leaves the system believing it is flat while it sits there."""
    long = intent(direction="long", slippage_tolerance=0.005)
    short = intent(direction="short", slippage_tolerance=0.005)

    assert long.limit_price() > long.reference_price
    assert short.limit_price() < short.reference_price


def test_every_intent_gets_a_client_id_before_it_is_sent():
    """Generated up front so an order is still recognisable when the response
    is lost, which is when it matters most."""
    first, second = intent(), intent()
    assert first.client_id != second.client_id
    assert first.client_id.startswith("hadrian-")


# --------------------------------------------------------------------------- #
# Dry run
# --------------------------------------------------------------------------- #


def test_a_dry_run_reports_what_it_would_have_done():
    receipt = DryRunExecutor().place(intent())

    assert receipt.accepted
    assert receipt.status == "simulated"
    assert receipt.filled_size == 0.00312
    assert "would buy" in receipt.message


def test_a_dry_run_never_invents_a_venue_order_id():
    """A fabricated id in the journal would be indistinguishable from a real
    one, and the journal is the one place that must never be ambiguous about
    whether something actually happened."""
    assert DryRunExecutor().place(intent()).venue_order_id is None


def test_a_dry_run_opens_no_socket(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("a dry run attempted a network connection")

    monkeypatch.setattr(httpx.Client, "post", explode)
    monkeypatch.setattr(httpx.Client, "request", explode)

    assert DryRunExecutor().place(intent()).accepted


def test_dry_run_is_what_build_executor_gives_you_by_default():
    from app.core.config import settings

    assert settings.EXECUTION_MODE is ExecutionMode.DRY_RUN
    assert isinstance(build_executor(settings.EXECUTION_MODE), DryRunExecutor)


# --------------------------------------------------------------------------- #
# Testnet
# --------------------------------------------------------------------------- #


def _response(handler) -> httpx.Response:
    """Run one request through the mock handler and return its response.

    The receipt reader is tested directly rather than through ``place()``,
    because ``place()`` signs first and the signing libraries are deliberately
    not installed by default.
    """
    request = httpx.Request("POST", "https://api.hyperliquid-testnet.xyz/exchange")
    response = handler(request)
    response.request = request
    return response


def make_executor(handler, **kwargs) -> TestnetExecutor:
    return testnet_module.TestnetExecutor(
        agent_key="0x" + "11" * 32,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        asset_index={"BTC": 0},
        **kwargs,
    )


def test_the_testnet_executor_refuses_to_exist_without_a_key(monkeypatch):
    monkeypatch.delenv("HL_TESTNET_AGENT_KEY", raising=False)
    executor = testnet_module.TestnetExecutor(client=httpx.Client())

    with pytest.raises(NotConfigured, match="HL_TESTNET_AGENT_KEY"):
        executor.place(intent())


def test_signing_is_not_available_in_a_default_install():
    """The strongest guarantee in this module is an absence, not a check: the
    signing libraries are not part of requirements.txt, so a default install
    cannot sign a transaction at all.

    If this fails because someone installed requirements-testnet.txt, that is
    the intended way to make it pass — but it should be a deliberate act.
    """
    from app.execution.testnet import _load_signing_dependencies

    try:
        import eth_account  # noqa: F401
        import msgpack  # noqa: F401
    except ImportError:
        with pytest.raises(NotConfigured, match="default install"):
            _load_signing_dependencies()
    else:
        pytest.skip("requirements-testnet.txt is installed in this environment")


def test_the_order_action_is_immediate_or_cancel():
    """A resting order would leave the system believing it is flat."""
    executor = make_executor(lambda request: httpx.Response(200))
    action = executor._order_action(intent())

    assert action["type"] == "order"
    assert action["orders"][0]["t"] == {"limit": {"tif": "Ioc"}}
    assert action["orders"][0]["b"] is True
    assert action["orders"][0]["a"] == 0


def test_sizes_are_sent_without_exponent_notation():
    """``repr`` renders a small BTC size as 1e-05, which the venue rejects."""
    executor = make_executor(lambda request: httpx.Response(200))
    action = executor._order_action(intent(size=0.00001))

    assert action["orders"][0]["s"] == "0.00001"
    assert "e" not in action["orders"][0]["s"]


def test_an_unknown_asset_is_refused_before_anything_is_sent():
    executor = make_executor(lambda request: httpx.Response(200))
    with pytest.raises(OrderRejected, match="asset index"):
        executor._order_action(intent(asset="DOGE"))


def test_a_filled_response_is_read_into_the_receipt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {
                        "statuses": [
                            {"filled": {"totalSz": "0.00312", "avgPx": "109100.0", "oid": 4242}}
                        ]
                    },
                },
            },
        )

    executor = make_executor(handler)
    receipt = executor._receipt(intent(), _response(handler))

    assert receipt.accepted
    assert receipt.status == "filled"
    assert receipt.venue_order_id == "4242"
    assert receipt.filled_size == pytest.approx(0.00312)
    assert receipt.average_price == pytest.approx(109100.0)


def test_a_refusal_from_the_venue_is_not_an_accepted_order():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "err", "response": "insufficient margin"})

    executor = make_executor(handler)
    receipt = executor._receipt(intent(), _response(handler))

    assert not receipt.accepted
    assert receipt.status == "rejected"
    assert "insufficient margin" in receipt.message


def test_an_unrecognised_response_shape_still_produces_a_receipt():
    """By this point the order has been sent; losing the receipt would be worse
    than losing the detail."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "response": {"unexpected": True}})

    executor = make_executor(handler)
    receipt = executor._receipt(intent(), _response(handler))

    assert receipt.accepted
    assert receipt.filled_size == 0.0
    assert receipt.venue_order_id is None


def test_the_testnet_executor_targets_the_testnet_host():
    executor = make_executor(lambda request: httpx.Response(200))
    assert "testnet" in executor._base_url


# --------------------------------------------------------------------------- #
# The gate, from the execution side
# --------------------------------------------------------------------------- #


def test_build_executor_refuses_mainnet():
    with pytest.raises(MainnetDisabled):
        build_executor(ExecutionMode.MAINNET)


def test_an_executor_that_could_sign_refuses_to_exist_in_a_refused_mode(monkeypatch):
    """The constructor gates as well as the factory: something that can sign
    should refuse to be built in a mode that must not sign, not merely refuse
    to act once it has been."""
    monkeypatch.setattr(testnet_module.TestnetExecutor, "mode", ExecutionMode.MAINNET)
    with pytest.raises(MainnetDisabled):
        testnet_module.TestnetExecutor(agent_key="0x" + "11" * 32)
