"""Parameter sweeps, and the topography they feed.

The sweep's whole purpose is to produce rows the *existing* topography endpoint
can read, so the tests end where that endpoint does: if a sweep runs and
``/systems/{id}/topography`` cannot draw it, the sweep did not work.
"""

from __future__ import annotations

import pytest
import sqlalchemy

from app.models import ParameterSweep, System
from app.services.sweep_service import MAX_SWEEP_CELLS, SweepTooLarge
from tests.integration.test_strategies_api import (  # noqa: F401 — fixtures
    StubCandleSource,
    backtest_range,
    candle_source,
    sma_cross_definition,
)


def swept_definition(name: str = "Swept") -> dict:
    """The SMA cross with both periods declared as swept parameters."""
    definition = sma_cross_definition(name)
    definition["parameters"] = {
        "fast": {"value": 5, "lo": 3, "hi": 9, "step": 2},
        "slow": {"value": 20, "lo": 15, "hi": 25, "step": 5},
    }
    definition["indicators"][0]["params"] = {"period": {"param": "fast"}}
    definition["indicators"][1]["params"] = {"period": {"param": "slow"}}
    return definition


@pytest.fixture()
def swept(client):
    response = client.post(
        "/strategies", json={"name": "Swept", "definition": swept_definition()}
    )
    assert response.status_code == 201, response.text
    return response.json()


def sweep_body(**overrides) -> dict:
    body = {"param_x": "fast", "param_y": "slow", "metric": "ev", **backtest_range()}
    body.update(overrides)
    return body


def test_a_sweep_produces_a_cell_per_parameter_combination(client, swept, candle_source):
    response = client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body())
    assert response.status_code == 200, response.text

    grid = response.json()
    # fast: 3,5,7,9 (4 values) × slow: 15,20,25 (3 values)
    assert len(grid["points"]) == 12
    assert {p["x"] for p in grid["points"]} == {3, 5, 7, 9}
    assert {p["y"] for p in grid["points"]} == {15, 20, 25}
    assert grid["param_x"] == "fast"
    assert grid["metric"] == "ev"


def test_the_cells_carry_enough_to_tell_flat_from_empty(client, swept, candle_source):
    """A cell that never traded and a cell that traded to nothing look
    identical on a heatmap unless the trade count travels with the value."""
    grid = client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body()).json()

    for point in grid["points"]:
        assert "n_trades" in point
        assert "total_r" in point
        assert "value" in point


def test_different_parameters_produce_different_cells(client, swept, candle_source):
    """A grid where every cell agreed would mean the overrides never reached
    the engine.

    Asserted on the scored value, not on the trade count. The fixture is a
    smooth sine with a whole number of cycles, so every moving-average pair
    catches the same crossings and every cell holds the same number of trades —
    which says nothing either way. What the parameters change here is where in
    each swing the entry lands, and that shows up in the expectancy.
    """
    grid = client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body()).json()
    values = {p["value"] for p in grid["points"]}
    assert len(values) > 1, "every parameter set produced the same expectancy"


def test_the_existing_topography_endpoint_can_draw_the_result(
    client, swept, candle_source
):
    """The endpoint is the acceptance test: the sweep exists to feed it."""
    grid = client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body()).json()

    topo = client.get(f"/systems/{grid['system_id']}/topography")
    assert topo.status_code == 200

    body = topo.json()
    assert len(body["grids"]) == 1
    drawn = body["grids"][0]
    assert drawn["param_x"] == "fast"
    assert drawn["x_values"] == [3, 5, 7, 9]
    assert drawn["y_values"] == [15, 20, 25]
    assert len(drawn["cells"]) == 12
    # The neighbourhood statistics are the reason this view exists.
    assert "robust_best" in drawn
    assert any(c["n_neighbors"] > 0 for c in drawn["cells"])


def test_a_sweep_leaves_the_baseline_system_behind(client, db_session, swept, candle_source):
    grid = client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body()).json()

    system = db_session.get(System, grid["system_id"])
    assert system.provenance == "engine"
    assert system.name == "Swept"


def test_re_running_the_same_axes_replaces_the_grid(client, db_session, swept, candle_source):
    """Two grids of the same thing would both be drawn."""
    client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body())
    client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body())

    stored = db_session.scalars(sqlalchemy.select(ParameterSweep)).all()
    assert len(stored) == 1


def test_sweeping_a_different_metric_is_a_separate_grid(client, db_session, swept, candle_source):
    client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body(metric="ev"))
    client.post(f"/strategies/{swept['id']}/sweep", json=sweep_body(metric="total_r"))

    stored = db_session.scalars(sqlalchemy.select(ParameterSweep)).all()
    assert len(stored) == 2


def test_an_undeclared_parameter_is_refused(client, swept, candle_source):
    response = client.post(
        f"/strategies/{swept['id']}/sweep", json=sweep_body(param_x="nonexistent")
    )
    assert response.status_code == 400
    assert "declares no parameter" in response.json()["detail"]


def test_a_parameter_without_a_range_cannot_be_an_axis(client, candle_source):
    definition = swept_definition("No range")
    definition["parameters"]["fast"] = {"value": 5}
    definition["indicators"][0]["params"] = {"period": {"param": "fast"}}

    created = client.post(
        "/strategies", json={"name": "No range", "definition": definition}
    ).json()
    response = client.post(f"/strategies/{created['id']}/sweep", json=sweep_body())

    assert response.status_code == 400
    assert "no range to sweep" in response.json()["detail"]


def test_a_lower_is_better_metric_is_refused(client, swept, candle_source):
    """The topography takes a maximum for ``best`` and ``robust_best``, which
    would silently invert the meaning of a drawdown."""
    response = client.post(
        f"/strategies/{swept['id']}/sweep", json=sweep_body(metric="max_drawdown_r")
    )
    assert response.status_code == 400
    assert "higher-is-better" in response.json()["detail"]


def test_an_oversized_grid_is_refused_with_the_arithmetic(client, candle_source):
    """Refused up front rather than attempted and abandoned halfway."""
    definition = swept_definition("Huge")
    definition["parameters"]["fast"] = {"value": 5, "lo": 1, "hi": 100, "step": 1}
    definition["parameters"]["slow"] = {"value": 20, "lo": 1, "hi": 100, "step": 1}

    created = client.post(
        "/strategies", json={"name": "Huge", "definition": definition}
    ).json()
    response = client.post(f"/strategies/{created['id']}/sweep", json=sweep_body())

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert "100×100" in detail
    assert str(MAX_SWEEP_CELLS) in detail


@pytest.mark.sandbox
def test_a_python_strategy_sweeps_in_a_single_sandbox_process(client, candle_source):
    """One spawn for the whole grid, not one per cell — and each cell still
    gets a fresh strategy instance so state cannot leak between them."""
    definition = swept_definition("Python swept")
    definition["rules"] = "python"
    definition["python_source"] = (
        "class Counting(Strategy):\n"
        "    def setup(self):\n"
        "        self.seen = 0\n"
        "    def on_bar(self, ctx):\n"
        "        self.seen += 1\n"
        "        fast, slow = ctx.indicator('fast'), ctx.indicator('slow')\n"
        "        pf, ps = ctx.indicator('fast', 1), ctx.indicator('slow', 1)\n"
        "        if None in (fast, slow, pf, ps):\n"
        "            return None\n"
        "        if ctx.position is None and pf <= ps and fast > slow:\n"
        "            return Signal.enter_long()\n"
        "        if ctx.position is not None and pf >= ps and fast < slow:\n"
        "            return Signal.exit()\n"
        "        return None\n"
    )
    for key in ("entry_long", "exit_long"):
        definition[key] = None

    created = client.post(
        "/strategies", json={"name": "Python swept", "definition": definition}
    ).json()
    response = client.post(f"/strategies/{created['id']}/sweep", json=sweep_body())

    assert response.status_code == 200, response.text
    grid = response.json()
    assert len(grid["points"]) == 12
    assert len({p["value"] for p in grid["points"]}) > 1
