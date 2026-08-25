"""The rule vocabulary served to the block designer.

The designer builds its palette from this, and the API then validates what the
designer produced against the Python schema. If the two ever disagree, the
designer offers something that cannot be saved — or, worse, silently omits
something the engine supports.

So these tests are almost entirely about the derivation staying total: every
literal the schema allows must appear, and nothing may appear that the schema
does not allow.
"""

from __future__ import annotations

import typing

from app.engine.indicators import INDICATOR_META, INDICATORS
from app.strategy.definition import (
    CROSSING,
    SCHEMA_VERSION,
    Comparator,
    IndicatorKind,
    PriceField,
)
from app.strategy.vocabulary import rule_vocabulary

VOCABULARY = rule_vocabulary()


def test_every_indicator_the_engine_can_compute_is_offered():
    offered = {i["kind"] for i in VOCABULARY["indicators"]}
    assert offered == set(INDICATORS)


def test_every_indicator_the_schema_allows_is_described():
    """Adding a kind to the schema without describing it would leave the
    designer unable to render it."""
    assert set(typing.get_args(IndicatorKind)) == set(INDICATOR_META)


def test_no_indicator_is_described_that_cannot_be_computed():
    """The other direction: metadata for a kind the engine does not implement
    would offer the user a strategy that validates and then fails to run."""
    assert set(INDICATOR_META) == set(INDICATORS)


def test_indicators_are_offered_in_the_schema_order():
    """So the palette and the type that validates it read the same way."""
    assert [i["kind"] for i in VOCABULARY["indicators"]] == list(
        typing.get_args(IndicatorKind)
    )


def test_every_described_indicator_declares_its_parameters():
    for indicator in VOCABULARY["indicators"]:
        assert indicator["params"], f"{indicator['kind']} declares no parameters"
        for param in indicator["params"]:
            assert {"name", "label", "default", "min"} <= set(param)
            assert param["default"] >= param["min"]


def test_atr_does_not_offer_a_source_field():
    """It reads high, low and close together; a source picker would be a
    control that does nothing."""
    atr = next(i for i in VOCABULARY["indicators"] if i["kind"] == "atr")
    assert atr["uses_source"] is False


def test_every_comparator_is_offered():
    assert {c["op"] for c in VOCABULARY["comparators"]} == set(
        typing.get_args(Comparator)
    )


def test_crossing_comparators_are_marked_as_refusing_an_offset():
    """The schema raises on an offset next to a crossing, so the designer has
    to know not to offer one."""
    for comparator in VOCABULARY["comparators"]:
        expected = comparator["op"] in CROSSING
        assert comparator["is_crossing"] is expected
        assert comparator["allows_offset"] is (not expected)


def test_every_price_field_is_offered():
    assert VOCABULARY["price_fields"] == list(typing.get_args(PriceField))


def test_timeframes_are_offered_shortest_first():
    from app.data.candles import TIMEFRAMES

    offered = VOCABULARY["timeframes"]
    assert set(offered) == set(TIMEFRAMES)
    assert offered == sorted(offered, key=lambda tf: TIMEFRAMES[tf])


def test_stop_kinds_say_which_need_an_indicator():
    """A stop kind that needs one and does not get one is refused by the
    schema, which the designer should prevent rather than discover."""
    by_kind = {s["kind"]: s for s in VOCABULARY["stop_kinds"]}
    assert by_kind["atr_multiple"]["requires_indicator"] is True
    assert by_kind["indicator"]["requires_indicator"] is True
    assert by_kind["percent"]["requires_indicator"] is False
    assert by_kind["fixed_points"]["requires_indicator"] is False


def test_target_kinds_say_which_need_an_indicator():
    by_kind = {t["kind"]: t for t in VOCABULARY["target_kinds"]}
    assert by_kind["indicator"]["requires_indicator"] is True
    assert by_kind["r_multiple"]["requires_indicator"] is False


def test_the_declared_requirements_match_what_the_schema_actually_enforces():
    """Guard the guard: the flags above are hand-written, so check each one
    against the validator rather than against the same assumption twice."""
    import pytest
    from pydantic import ValidationError

    from app.strategy.definition import StopSpec, TargetSpec

    for stop in VOCABULARY["stop_kinds"]:
        if stop["requires_indicator"]:
            with pytest.raises(ValidationError):
                StopSpec(kind=stop["kind"], value=2.0)
        else:
            StopSpec(kind=stop["kind"], value=2.0)

    for target in VOCABULARY["target_kinds"]:
        if target["requires_indicator"]:
            with pytest.raises(ValidationError):
                TargetSpec(kind=target["kind"], value=2.0)
        else:
            TargetSpec(kind=target["kind"], value=2.0)


def test_the_cost_defaults_are_the_verified_venue_figures():
    costs = VOCABULARY["cost_defaults"]
    assert costs["entry_fee_pct"] == 0.000144
    assert costs["exit_fee_pct"] == 0.000432


def test_the_vocabulary_states_the_schema_it_describes():
    assert VOCABULARY["schema_version"] == SCHEMA_VERSION


def test_position_fields_are_offered_for_exit_rules():
    assert set(VOCABULARY["position_fields"]) == {
        "bars_held",
        "unrealised_r",
        "entry_price",
        "direction_sign",
    }


def test_the_whole_vocabulary_is_json_serialisable():
    """It is served over HTTP; a stray Literal or type object would 500."""
    import json

    json.dumps(VOCABULARY)


def test_the_vocabulary_says_where_position_state_may_be_used():
    """The schema refuses a position operand in an entry rule or a filter, so
    the designer needs to know not to offer it there."""
    allowed = {
        slot["slot"] for slot in VOCABULARY["rule_slots"] if slot["allows_position"]
    }
    assert allowed == {"exit_long", "exit_short"}
    assert set(VOCABULARY["position_operand_slots"]) == allowed


def test_every_rule_slot_the_schema_has_is_described():
    """A slot missing from the vocabulary is a rule the designer cannot edit."""
    from app.strategy.definition import StrategyDefinition

    described = {slot["slot"] for slot in VOCABULARY["rule_slots"]}
    actual = {
        name
        for name in ("entry_long", "entry_short", "exit_long", "exit_short", "filters")
        if name in StrategyDefinition.model_fields
    }
    assert described == actual


def test_the_declared_position_slots_match_what_the_schema_enforces():
    """Guard the guard: check each flag against the validator rather than
    against the same assumption twice."""
    import pytest
    from pydantic import ValidationError

    from tests.test_strategy_definition import position_rule, sma_cross

    for slot in VOCABULARY["rule_slots"]:
        payload = (
            {slot["slot"]: [position_rule()]}
            if slot["slot"] == "filters"
            else {slot["slot"]: position_rule()}
        )
        if slot["allows_position"]:
            sma_cross(**payload)
        else:
            with pytest.raises(ValidationError, match="only available to exit rules"):
                sma_cross(**payload)
