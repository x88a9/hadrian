"""The Strategy Definition: round-tripping, validation, parameter resolution.

The definition is the contract between both authoring paths and the engine, so
these tests care less about happy-path construction than about what it refuses.
Everything caught here is a mistake that would otherwise surface hundreds of
bars into a backtest, or not at all.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.strategy.definition import (
    SCHEMA_VERSION,
    BoolNode,
    Comparison,
    ConstOperand,
    CostSpec,
    IndicatorOperand,
    IndicatorSpec,
    ParameterSpec,
    ParamRef,
    PositionOperand,
    PriceOperand,
    RiskSpec,
    StopSpec,
    StrategyDefinition,
    StrategyDefinitionError,
    TargetSpec,
)


def sma_cross(**overrides) -> StrategyDefinition:
    """A minimal but complete long-only definition, used as a base to break."""
    kwargs = dict(
        name="SMA cross",
        asset="BTC",
        timeframe="H1",
        direction="long",
        parameters={
            "fast": ParameterSpec(value=10, lo=5, hi=20, step=5),
            "slow": ParameterSpec(value=30),
        },
        indicators=[
            IndicatorSpec(id="sma_fast", kind="sma", params={"period": ParamRef(param="fast")}),
            IndicatorSpec(id="sma_slow", kind="sma", params={"period": ParamRef(param="slow")}),
            IndicatorSpec(id="atr14", kind="atr", params={"period": 14.0}),
        ],
        entry_long=Comparison(
            left=IndicatorOperand(id="sma_fast"),
            cmp="cross_above",
            right=IndicatorOperand(id="sma_slow"),
        ),
        exit_long=Comparison(
            left=IndicatorOperand(id="sma_fast"),
            cmp="cross_below",
            right=IndicatorOperand(id="sma_slow"),
        ),
        risk=RiskSpec(
            stop=StopSpec(kind="atr_multiple", value=2.0, indicator_id="atr14"),
            target=TargetSpec(kind="r_multiple", value=3.0),
        ),
    )
    kwargs.update(overrides)
    return StrategyDefinition(**kwargs)


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #


def test_round_trips_through_json_unchanged():
    original = sma_cross()
    encoded = json.dumps(original.to_json_dict())
    restored = StrategyDefinition.from_json_dict(json.loads(encoded))
    assert restored.to_json_dict() == original.to_json_dict()
    assert restored == original


def test_round_trip_keeps_explicit_nulls():
    """An absent field and a cleared one must stay distinguishable, or the
    designer cannot tell "never set" from "set back to nothing"."""
    d = sma_cross(risk=RiskSpec(stop=StopSpec(kind="percent", value=1.0), target=None))
    payload = d.to_json_dict()
    assert "target" in payload["risk"]
    assert payload["risk"]["target"] is None
    assert StrategyDefinition.from_json_dict(payload).risk.target is None


def test_refuses_a_definition_from_a_future_schema():
    payload = sma_cross().to_json_dict()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(StrategyDefinitionError, match="schema_version"):
        StrategyDefinition.from_json_dict(payload)


def test_refuses_something_that_is_not_a_definition():
    with pytest.raises(StrategyDefinitionError):
        StrategyDefinition.from_json_dict(["not", "an", "object"])  # type: ignore[arg-type]


def test_load_error_is_the_definition_error_not_a_pydantic_one():
    """Callers should catch one exception type, not two."""
    payload = sma_cross().to_json_dict()
    payload["risk"]["stop"]["kind"] = "nonsense"
    with pytest.raises(StrategyDefinitionError):
        StrategyDefinition.from_json_dict(payload)


def test_unknown_fields_are_refused():
    """Silently dropping a misspelled key is how a rule goes quietly missing."""
    payload = sma_cross().to_json_dict()
    payload["entry_lng"] = payload.pop("entry_long")
    with pytest.raises(StrategyDefinitionError):
        StrategyDefinition.from_json_dict(payload)


# --------------------------------------------------------------------------- #
# Lookahead is unrepresentable
# --------------------------------------------------------------------------- #


def test_a_negative_price_offset_cannot_be_expressed():
    with pytest.raises(ValidationError):
        PriceOperand(field="close", offset=-1)


def test_a_negative_indicator_offset_cannot_be_expressed():
    with pytest.raises(ValidationError):
        IndicatorOperand(id="sma_fast", offset=-1)


def test_a_crossing_comparator_refuses_an_offset():
    """cross_above already means "bar t versus bar t-1"; an offset on top of
    that is either a misunderstanding or a reach for a bar that is not there."""
    with pytest.raises(ValidationError, match="cannot take an offset"):
        sma_cross(
            entry_long=Comparison(
                left=IndicatorOperand(id="sma_fast", offset=2),
                cmp="cross_above",
                right=IndicatorOperand(id="sma_slow"),
            )
        )


# --------------------------------------------------------------------------- #
# Referential validation
# --------------------------------------------------------------------------- #


def test_refuses_a_rule_referencing_an_undeclared_indicator():
    with pytest.raises(ValidationError, match="unknown indicator 'ema200'"):
        sma_cross(
            filters=[
                Comparison(
                    left=PriceOperand(field="close"),
                    cmp=">",
                    right=IndicatorOperand(id="ema200"),
                )
            ]
        )


def test_refuses_a_stop_referencing_an_undeclared_indicator():
    with pytest.raises(ValidationError, match="unknown indicator"):
        sma_cross(
            risk=RiskSpec(stop=StopSpec(kind="atr_multiple", value=2.0, indicator_id="atr99"))
        )


def test_refuses_duplicate_indicator_ids():
    with pytest.raises(ValidationError, match="duplicate indicator ids"):
        sma_cross(
            indicators=[
                IndicatorSpec(id="sma_fast", kind="sma", params={"period": 10.0}),
                IndicatorSpec(id="sma_fast", kind="ema", params={"period": 50.0}),
                IndicatorSpec(id="atr14", kind="atr", params={"period": 14.0}),
                IndicatorSpec(id="sma_slow", kind="sma", params={"period": 30.0}),
            ]
        )


def test_refuses_an_undeclared_parameter_reference():
    with pytest.raises(ValidationError, match="undeclared parameter 'middle'"):
        sma_cross(
            indicators=[
                IndicatorSpec(id="sma_fast", kind="sma", params={"period": ParamRef(param="middle")}),
                IndicatorSpec(id="sma_slow", kind="sma", params={"period": 30.0}),
                IndicatorSpec(id="atr14", kind="atr", params={"period": 14.0}),
            ]
        )


def test_atr_stop_requires_an_indicator():
    with pytest.raises(ValidationError, match="requires indicator_id"):
        StopSpec(kind="atr_multiple", value=2.0)


def test_boolean_node_arity_is_enforced():
    term = Comparison(left=PriceOperand(), cmp=">", right=ConstOperand(value=0.0))
    with pytest.raises(ValidationError, match="exactly one term"):
        BoolNode(node="not", terms=[term, term])
    with pytest.raises(ValidationError, match="at least one term"):
        BoolNode(node="all", terms=[])


# --------------------------------------------------------------------------- #
# Direction consistency
# --------------------------------------------------------------------------- #


def test_long_only_strategy_refuses_a_short_entry():
    with pytest.raises(ValidationError, match="direction is 'long' but entry_short"):
        sma_cross(
            entry_short=Comparison(
                left=IndicatorOperand(id="sma_fast"),
                cmp="cross_below",
                right=IndicatorOperand(id="sma_slow"),
            )
        )


def test_a_direction_without_its_entry_rule_is_refused():
    with pytest.raises(ValidationError, match="entry_short is unset"):
        sma_cross(direction="both")


def test_both_directions_accepted_when_both_rules_are_present():
    d = sma_cross(
        direction="both",
        entry_short=Comparison(
            left=IndicatorOperand(id="sma_fast"),
            cmp="cross_below",
            right=IndicatorOperand(id="sma_slow"),
        ),
    )
    assert d.direction == "both"


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #


def test_resolve_substitutes_every_reference():
    d = sma_cross()
    assert not d.is_resolved

    r = d.resolve()
    assert r.is_resolved
    assert r.indicators[0].params["period"] == 10.0
    assert r.indicators[1].params["period"] == 30.0


def test_resolve_applies_overrides():
    r = sma_cross().resolve({"fast": 15, "slow": 60})
    assert r.indicators[0].params["period"] == 15.0
    assert r.indicators[1].params["period"] == 60.0


def test_a_resolved_definition_reports_the_values_it_ran_with():
    """What ran is what the stored definition says ran — otherwise a swept
    result cannot be traced back to the parameters that produced it."""
    r = sma_cross().resolve({"fast": 15})
    assert r.parameters["fast"].value == 15.0
    assert r.parameters["fast"].lo == 5.0  # the declared range survives


def test_resolve_refuses_an_undeclared_override():
    with pytest.raises(StrategyDefinitionError, match="undeclared parameters"):
        sma_cross().resolve({"nonexistent": 1.0})


def test_resolving_twice_is_a_no_op():
    once = sma_cross().resolve({"fast": 15})
    assert once.resolve().to_json_dict() == once.to_json_dict()


def test_a_resolved_definition_still_round_trips():
    r = sma_cross().resolve({"fast": 15})
    assert StrategyDefinition.from_json_dict(r.to_json_dict()) == r


def test_sweep_grid_hits_both_endpoints():
    assert ParameterSpec(value=10, lo=5, hi=20, step=5).sweep_values() == [5, 10, 15, 20]


def test_sweep_grid_of_a_fractional_step_does_not_drift():
    """Accumulated addition would land on 1.9999999999999998 rather than 2.0."""
    values = ParameterSpec(value=1.0, lo=1.0, hi=2.0, step=0.1).sweep_values()
    assert values[-1] == 2.0
    assert len(values) == 11


def test_an_unannotated_parameter_contributes_only_its_value():
    """A partly-annotated strategy still sweeps; it just does not vary that axis."""
    assert ParameterSpec(value=30).sweep_values() == [30]


def test_refuses_an_inverted_parameter_range():
    with pytest.raises(ValidationError, match="inverted"):
        ParameterSpec(value=10, lo=20, hi=5, step=1)


def test_refuses_a_non_positive_step():
    with pytest.raises(ValidationError, match="step must be positive"):
        ParameterSpec(value=10, lo=1, hi=5, step=0)


# --------------------------------------------------------------------------- #
# Costs and shape
# --------------------------------------------------------------------------- #


def test_cost_defaults_match_the_verified_live_trading_figures():
    """These are the same taker fees the live-trading module was verified
    against; a backtest and a live ticket must not disagree about costs."""
    costs = CostSpec()
    assert costs.entry_fee_pct == 0.000144
    assert costs.exit_fee_pct == 0.000432
    assert costs.slippage_pct == 0.0


def test_negative_costs_are_refused():
    with pytest.raises(ValidationError):
        CostSpec(entry_fee_pct=-0.001)


def test_a_definition_is_immutable():
    """The engine holds one across a whole backtest; it must not be mutated
    halfway through by anything it is handed to."""
    d = sma_cross()
    with pytest.raises(ValidationError):
        d.name = "something else"  # type: ignore[misc]


def test_position_operands_are_available_to_exit_rules():
    d = sma_cross(
        exit_long=BoolNode(
            node="any",
            terms=[
                Comparison(
                    left=PositionOperand(field="unrealised_r"),
                    cmp=">=",
                    right=ConstOperand(value=2.0),
                ),
                Comparison(
                    left=PositionOperand(field="bars_held"),
                    cmp=">",
                    right=ConstOperand(value=48.0),
                ),
            ],
        )
    )
    assert StrategyDefinition.from_json_dict(d.to_json_dict()) == d


def test_only_one_concurrent_position_is_expressible():
    """The engine implements one position at a time; a definition assuming
    otherwise is refused rather than silently mis-executed."""
    with pytest.raises(ValidationError):
        RiskSpec(stop=StopSpec(kind="percent", value=1.0), max_concurrent_positions=2)


# --------------------------------------------------------------------------- #
# The two rule carriers
# --------------------------------------------------------------------------- #

PYTHON_RULES = "class S(Strategy):\n    def on_bar(self, ctx):\n        return None\n"


def python_strategy(**overrides) -> StrategyDefinition:
    kwargs = dict(
        name="Written in Python",
        asset="BTC",
        timeframe="H1",
        direction="long",
        rules="python",
        python_source=PYTHON_RULES,
        indicators=[IndicatorSpec(id="atr14", kind="atr", params={"period": 14.0})],
        risk=RiskSpec(stop=StopSpec(kind="atr_multiple", value=2.0, indicator_id="atr14")),
    )
    kwargs.update(overrides)
    return StrategyDefinition(**kwargs)


def test_a_python_strategy_needs_no_declarative_entry_rule():
    d = python_strategy()
    assert d.rules == "python"
    assert d.entry_long is None


def test_a_python_strategy_round_trips():
    d = python_strategy()
    assert StrategyDefinition.from_json_dict(d.to_json_dict()) == d
    assert StrategyDefinition.from_json_dict(d.to_json_dict()).python_source == PYTHON_RULES


def test_a_python_strategy_shares_the_metadata_both_paths_use():
    """The shared half is what makes a hand-written strategy sweepable and
    storable exactly like a designed one."""
    d = python_strategy(
        parameters={"lookback": ParameterSpec(value=20, lo=10, hi=40, step=10)}
    )
    assert d.parameters["lookback"].sweep_values() == [10, 20, 30, 40]
    assert d.risk.stop.indicator_id == "atr14"
    assert d.costs.entry_fee_pct == 0.000144


def test_python_rules_refuse_an_empty_source():
    with pytest.raises(ValidationError, match="python_source is empty"):
        python_strategy(python_source="   ")


def test_a_definition_cannot_carry_both_kinds_of_rule():
    """Two answers to "when does this buy" and no way to say which one ran."""
    with pytest.raises(ValidationError, match="rules is 'python'"):
        python_strategy(
            entry_long=Comparison(
                left=PriceOperand(), cmp=">", right=ConstOperand(value=0.0)
            )
        )


def test_python_rules_refuse_declarative_filters():
    with pytest.raises(ValidationError, match="filters belong in the source"):
        python_strategy(
            filters=[Comparison(left=PriceOperand(), cmp=">", right=ConstOperand(value=0.0))]
        )


def test_declarative_rules_refuse_a_stray_python_source():
    with pytest.raises(ValidationError, match="clear one of them"):
        sma_cross(python_source=PYTHON_RULES)


def test_declarative_is_the_default_carrier():
    assert sma_cross().rules == "declarative"
    assert sma_cross().python_source is None


# --------------------------------------------------------------------------- #
# Position state belongs to exit rules
# --------------------------------------------------------------------------- #


def position_rule() -> Comparison:
    return Comparison(
        left=PositionOperand(field="bars_held"),
        cmp=">",
        right=ConstOperand(value=5.0),
    )


def test_an_entry_rule_cannot_read_position_state():
    """It would validate and then never fire: entry rules run while flat, so
    the comparison is false on every bar. That is indistinguishable from a
    setup that genuinely never occurred, which is the worst way to be wrong."""
    with pytest.raises(ValidationError, match="only available to exit rules"):
        sma_cross(entry_long=position_rule())


def test_a_filter_cannot_read_position_state():
    """Filters gate entries, so they see the same permanent absence."""
    with pytest.raises(ValidationError, match="only available to exit rules"):
        sma_cross(filters=[position_rule()])


def test_position_state_nested_inside_an_entry_rule_is_also_caught():
    with pytest.raises(ValidationError, match="only available to exit rules"):
        sma_cross(
            entry_long=BoolNode(
                node="all",
                terms=[
                    Comparison(
                        left=IndicatorOperand(id="sma_fast"),
                        cmp="cross_above",
                        right=IndicatorOperand(id="sma_slow"),
                    ),
                    BoolNode(node="not", terms=[position_rule()]),
                ],
            )
        )


def test_an_exit_rule_may_read_position_state():
    """Where there is a position to read."""
    d = sma_cross(exit_long=position_rule())
    assert d.exit_long.left.field == "bars_held"
