"""The strategy designer's API, end to end against Postgres.

No test here touches the network: the candle source is a fixture serving a
deterministic synthetic series, injected through the same FastAPI dependency
the real source uses. A suite that reached the venue would be slow, flaky and
dependent on what the market did last Tuesday.

The test that matters most is the one asserting an engine backtest cannot
overwrite an imported system. Engine results deliberately land in the same
tables as the imported ones so the existing analytics read them unchanged, and
that is precisely what makes a name collision dangerous: the imported figures
are reconciled cell by cell against the research workbook, and a backtest
quietly replacing them would be very hard to notice and impossible to undo.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy

from app.api.strategies import get_candle_source
from app.data.candles import Candle, CandleSeries
from app.main import app
from app.models import BacktestRun, Strategy, StrategyVersion, System, Trade

BASE = datetime(2022, 1, 1, tzinfo=timezone.utc)


class StubCandleSource:
    """A deterministic drifting sine, sliced to whatever range is asked for."""

    def __init__(self, n: int = 400):
        candles = []
        previous_close = 100.0
        for i in range(n):
            close = 100 + i * 0.2 + 8 * math.sin(i / 9)
            open_ = previous_close
            candles.append(
                Candle(
                    BASE + timedelta(hours=i),
                    open_,
                    max(open_, close) + 0.6,
                    min(open_, close) - 0.6,
                    close,
                    1.0,
                )
            )
            previous_close = close
        self._series = CandleSeries("BTC", "1h", candles)
        self.calls: list[tuple] = []

    def fetch(self, asset, timeframe, start, end):
        self.calls.append((asset, timeframe, start, end))
        return self._series.slice(start, end)


@pytest.fixture()
def candle_source():
    source = StubCandleSource()
    app.dependency_overrides[get_candle_source] = lambda: source
    try:
        yield source
    finally:
        app.dependency_overrides.pop(get_candle_source, None)


def sma_cross_definition(name: str = "SMA cross", **extra) -> dict:
    definition = {
        "schema_version": 1,
        "name": name,
        "asset": "BTC",
        "timeframe": "1h",
        "direction": "long",
        "indicators": [
            {"id": "fast", "kind": "sma", "source": "close", "params": {"period": 5}},
            {"id": "slow", "kind": "sma", "source": "close", "params": {"period": 20}},
            {"id": "atr", "kind": "atr", "source": "close", "params": {"period": 14}},
        ],
        "entry_long": {
            "node": "compare",
            "left": {"op": "indicator", "id": "fast", "offset": 0},
            "cmp": "cross_above",
            "right": {"op": "indicator", "id": "slow", "offset": 0},
        },
        "exit_long": {
            "node": "compare",
            "left": {"op": "indicator", "id": "fast", "offset": 0},
            "cmp": "cross_below",
            "right": {"op": "indicator", "id": "slow", "offset": 0},
        },
        "risk": {
            "stop": {"kind": "atr_multiple", "value": 2.0, "indicator_id": "atr"},
            "target": {"kind": "r_multiple", "value": 3.0},
            "max_concurrent_positions": 1,
        },
    }
    definition.update(extra)
    return definition


@pytest.fixture()
def strategy(client):
    response = client.post(
        "/strategies",
        json={"name": "SMA cross", "definition": sma_cross_definition()},
    )
    assert response.status_code == 201, response.text
    return response.json()


def backtest_range() -> dict:
    return {
        "start": BASE.isoformat(),
        "end": (BASE + timedelta(hours=400)).isoformat(),
    }


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


def test_creating_a_strategy_stores_version_one(client, db_session, strategy):
    assert strategy["current_version"] == 1
    assert strategy["asset"] == "BTC"
    assert strategy["rules"] == "declarative"
    assert [v["version"] for v in strategy["versions"]] == [1]

    stored = db_session.scalars(sqlalchemy.select(StrategyVersion)).all()
    assert len(stored) == 1
    assert stored[0].definition["name"] == "SMA cross"


def test_a_duplicate_name_is_a_conflict(client, strategy):
    response = client.post(
        "/strategies",
        json={"name": "SMA cross", "definition": sma_cross_definition()},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_an_invalid_definition_is_refused_at_creation(client):
    broken = sma_cross_definition()
    broken["risk"]["stop"] = {"kind": "atr_multiple", "value": 2.0}  # no indicator_id
    response = client.post("/strategies", json={"name": "Broken", "definition": broken})
    assert response.status_code == 422


def test_saving_writes_a_new_version_and_never_edits_an_old_one(client, strategy):
    original = client.get(f"/strategies/{strategy['id']}").json()
    v1_definition = original["versions"][0]["definition"]

    updated = sma_cross_definition()
    updated["indicators"][0]["params"]["period"] = 9
    response = client.put(
        f"/strategies/{strategy['id']}",
        json={"definition": updated, "note": "faster"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["current_version"] == 2
    assert body["definition"]["indicators"][0]["params"]["period"] == 9
    versions = {v["version"]: v for v in body["versions"]}
    assert versions[1]["definition"] == v1_definition, "version 1 was rewritten"
    assert versions[2]["note"] == "faster"


def test_restoring_an_old_version_appends_rather_than_rewinding(client, strategy):
    """"Went back to v1" is recorded as v3. Rewinding would leave the versions
    in between unexplainable."""
    faster = sma_cross_definition()
    faster["indicators"][0]["params"]["period"] = 9
    client.put(f"/strategies/{strategy['id']}", json={"definition": faster})

    v1 = client.get(f"/strategies/{strategy['id']}/versions/1").json()
    response = client.put(
        f"/strategies/{strategy['id']}",
        json={"definition": v1["definition"], "note": "restored v1"},
    )

    body = response.json()
    assert body["current_version"] == 3
    assert len(body["versions"]) == 3
    assert body["definition"]["indicators"][0]["params"]["period"] == 5


def test_duplicating_starts_a_fresh_history(client, strategy):
    client.put(
        f"/strategies/{strategy['id']}", json={"definition": sma_cross_definition()}
    )
    response = client.post(
        f"/strategies/{strategy['id']}/duplicate", json={"name": "SMA cross (slow)"}
    )
    assert response.status_code == 201

    copy = response.json()
    assert copy["id"] != strategy["id"]
    assert copy["current_version"] == 1
    assert copy["definition"]["name"] == "SMA cross (slow)"


def test_deleting_a_strategy_takes_its_versions_and_runs_with_it(
    client, db_session, strategy, candle_source
):
    client.post(f"/strategies/{strategy['id']}/backtest", json=backtest_range())
    assert client.delete(f"/strategies/{strategy['id']}").status_code == 204

    assert db_session.scalars(sqlalchemy.select(Strategy)).all() == []
    assert db_session.scalars(sqlalchemy.select(StrategyVersion)).all() == []
    assert db_session.scalars(sqlalchemy.select(BacktestRun)).all() == []


def test_an_unknown_strategy_is_a_404(client):
    assert client.get("/strategies/9999").status_code == 404


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def test_validation_reports_problems_without_failing_the_request(client):
    """The client is asking a question about a draft; a draft being invalid is
    the answer, not a failed request."""
    broken = sma_cross_definition()
    broken["entry_long"]["left"]["id"] = "nonexistent"

    response = client.post("/strategies/validate", json={"definition": broken})
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is False
    assert body["errors"]
    assert any("nonexistent" in e for e in body["errors"])


def test_validation_accepts_a_good_definition(client):
    response = client.post(
        "/strategies/validate", json={"definition": sma_cross_definition()}
    )
    body = response.json()
    assert body["ok"] is True
    assert body["errors"] == []
    assert body["definition"]["name"] == "SMA cross"


def test_validation_does_not_store_anything(client, db_session):
    client.post("/strategies/validate", json={"definition": sma_cross_definition()})
    assert db_session.scalars(sqlalchemy.select(Strategy)).all() == []


# --------------------------------------------------------------------------- #
# Backtesting
# --------------------------------------------------------------------------- #


def test_a_backtest_returns_trades_and_platform_metrics(
    client, strategy, candle_source
):
    response = client.post(
        f"/strategies/{strategy['id']}/backtest", json=backtest_range()
    )
    assert response.status_code == 200, response.text

    run = response.json()
    assert run["status"] == "ok"
    assert run["bars"] > 0
    assert run["trades"], "the fixture should produce trades"
    assert set(run["metrics"]) == {"all", "is", "oos"}
    assert run["metrics"]["all"]["total_trades"] == len(run["trades"])


def test_a_backtest_does_not_persist_a_system_unless_asked(
    client, db_session, strategy, candle_source
):
    """An exploratory run should not leave a system behind."""
    run = client.post(
        f"/strategies/{strategy['id']}/backtest", json=backtest_range()
    ).json()
    assert run["system_id"] is None
    assert db_session.scalars(sqlalchemy.select(System)).all() == []


def test_persisting_writes_an_engine_system_the_existing_analytics_can_read(
    client, db_session, strategy, candle_source
):
    run = client.post(
        f"/strategies/{strategy['id']}/backtest",
        json={**backtest_range(), "persist": True},
    ).json()

    assert run["system_id"] is not None
    system = db_session.get(System, run["system_id"])
    assert system.provenance == "engine"
    assert system.origin == "ui"
    assert system.asset == "BTC"

    trades = db_session.scalars(
        sqlalchemy.select(Trade).where(Trade.system_id == system.id)
    ).all()
    assert len(trades) == len(run["trades"])
    assert all(t.source == "auto" for t in trades)
    assert all(t.r_value is not None for t in trades)

    # The existing metrics endpoint reads it with no idea it came from the engine.
    detail = client.get(f"/systems/{system.id}").json()
    assert detail["metrics"]["all"]["total_trades"] == len(trades)


def test_re_running_replaces_the_trades_rather_than_appending(
    client, db_session, strategy, candle_source
):
    """Appending would silently double every trade count on the second run."""
    first = client.post(
        f"/strategies/{strategy['id']}/backtest",
        json={**backtest_range(), "persist": True},
    ).json()
    second = client.post(
        f"/strategies/{strategy['id']}/backtest",
        json={**backtest_range(), "persist": True},
    ).json()

    assert first["system_id"] == second["system_id"]

    trades = db_session.scalars(
        sqlalchemy.select(Trade).where(Trade.system_id == second["system_id"])
    ).all()
    assert len(trades) == len(second["trades"])


def test_the_engine_refuses_to_overwrite_an_imported_system(
    client, db_session, candle_source
):
    """The load-bearing safety property of persistence.

    Imported systems carry figures reconciled against the research workbook. A
    backtest that shares a name must not touch them — and there is no version
    of merging the two that would be correct, so it refuses outright.
    """
    imported = System(
        name="Collision",
        provenance="programmatic",
        source_engine="hadrian2",
        import_status="complete",
        status="backtest",
    )
    db_session.add(imported)
    db_session.add(Trade(system=imported, r_value=1.0, win_loss="win", source="auto"))
    db_session.commit()

    created = client.post(
        "/strategies",
        json={"name": "Collision", "definition": sma_cross_definition("Collision")},
    ).json()

    response = client.post(
        f"/strategies/{created['id']}/backtest",
        json={**backtest_range(), "persist": True},
    )
    assert response.status_code == 409
    assert "will not overwrite imported results" in response.json()["detail"]

    db_session.expire_all()
    survivor = db_session.get(System, imported.id)
    assert survivor.provenance == "programmatic"
    assert len(survivor.trades) == 1, "the imported trades were touched"


def test_parameter_overrides_are_recorded_with_the_run(client, candle_source):
    definition = sma_cross_definition("Swept")
    definition["parameters"] = {"fast": {"value": 5, "lo": 3, "hi": 15, "step": 2}}
    definition["indicators"][0]["params"] = {"period": {"param": "fast"}}

    created = client.post(
        "/strategies", json={"name": "Swept", "definition": definition}
    ).json()

    run = client.post(
        f"/strategies/{created['id']}/backtest",
        json={**backtest_range(), "overrides": {"fast": 11}},
    ).json()

    assert run["overrides"] == {"fast": 11.0}
    assert run["status"] == "ok"


def test_a_failing_strategy_is_recorded_rather_than_lost(client, candle_source):
    """"This version does not run, and here is why" is a result about the
    strategy; losing it would leave only a toast the user already dismissed."""
    definition = sma_cross_definition("Explodes")
    definition["rules"] = "python"
    definition["python_source"] = (
        "class Boom(Strategy):\n"
        "    def on_bar(self, ctx):\n"
        "        raise ValueError('deliberate')\n"
    )
    for key in ("entry_long", "exit_long"):
        definition[key] = None

    created = client.post(
        "/strategies", json={"name": "Explodes", "definition": definition}
    ).json()

    response = client.post(
        f"/strategies/{created['id']}/backtest", json=backtest_range()
    )
    assert response.status_code == 200

    run = response.json()
    assert run["status"] == "failed"
    assert "deliberate" in run["error"]
    assert run["trades"] == []

    listed = client.get(f"/strategies/{created['id']}/backtests").json()
    assert [r["id"] for r in listed] == [run["id"]]


def test_a_run_can_be_fetched_again_by_id(client, strategy, candle_source):
    run = client.post(
        f"/strategies/{strategy['id']}/backtest", json=backtest_range()
    ).json()

    again = client.get(f"/backtests/{run['id']}").json()
    assert again["id"] == run["id"]
    assert again["trades"] == run["trades"]


def test_the_list_view_reports_the_latest_result(client, strategy, candle_source):
    client.post(f"/strategies/{strategy['id']}/backtest", json=backtest_range())

    listed = client.get("/strategies").json()
    row = next(s for s in listed if s["id"] == strategy["id"])
    assert row["last_backtest_at"] is not None
    assert row["last_total_r"] is not None


def test_backtesting_a_specific_version_uses_that_version(client, strategy, candle_source):
    faster = sma_cross_definition()
    faster["indicators"][0]["params"]["period"] = 9
    client.put(f"/strategies/{strategy['id']}", json={"definition": faster})

    on_v1 = client.post(
        f"/strategies/{strategy['id']}/backtest", json={**backtest_range(), "version": 1}
    ).json()
    on_v2 = client.post(
        f"/strategies/{strategy['id']}/backtest", json={**backtest_range(), "version": 2}
    ).json()

    assert on_v1["version"] == 1
    assert on_v2["version"] == 2
    assert on_v1["trades"] != on_v2["trades"]


def test_an_unknown_version_is_a_400_not_a_crash(client, strategy, candle_source):
    response = client.post(
        f"/strategies/{strategy['id']}/backtest",
        json={**backtest_range(), "version": 99},
    )
    assert response.status_code == 400
    assert "no version 99" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# The rule vocabulary the block designer builds from
# --------------------------------------------------------------------------- #


def test_the_schema_endpoint_is_not_shadowed_by_the_id_route(client):
    """``/strategies/schema`` and ``/strategies/{strategy_id}`` are both GETs on
    a two-segment path; the literal one has to be declared first or "schema"
    gets parsed as an id."""
    response = client.get("/strategies/schema")
    assert response.status_code == 200
    assert "indicators" in response.json()


def test_the_vocabulary_covers_what_a_definition_needs(client):
    body = client.get("/strategies/schema").json()

    for key in (
        "indicators",
        "comparators",
        "price_fields",
        "operand_kinds",
        "position_fields",
        "bool_nodes",
        "stop_kinds",
        "target_kinds",
        "timeframes",
        "directions",
        "cost_defaults",
    ):
        assert body.get(key), f"the designer cannot build without {key}"


def test_a_definition_assembled_from_the_vocabulary_validates(client):
    """The point of serving it: everything the palette offers must be something
    the validator accepts."""
    body = client.get("/strategies/schema").json()

    indicator_kind = body["indicators"][0]["kind"]
    period = body["indicators"][0]["params"][0]
    stop_kind = next(s for s in body["stop_kinds"] if not s["requires_indicator"])

    definition = {
        "schema_version": body["schema_version"],
        "name": "Assembled from the palette",
        "asset": "BTC",
        "timeframe": body["timeframes"][5],
        "direction": body["directions"][0],
        "indicators": [
            {
                "id": "ind",
                "kind": indicator_kind,
                "source": body["price_fields"][3],
                "params": {period["name"]: period["default"]},
            }
        ],
        "entry_long": {
            "node": "compare",
            "left": {"op": "price", "field": body["price_fields"][3], "offset": 0},
            "cmp": ">",
            "right": {"op": "indicator", "id": "ind", "offset": 0},
        },
        "risk": {"stop": {"kind": stop_kind["kind"], "value": 1.0}},
        "costs": body["cost_defaults"],
    }

    validated = client.post("/strategies/validate", json={"definition": definition})
    assert validated.status_code == 200
    assert validated.json()["ok"] is True, validated.json()["errors"]
