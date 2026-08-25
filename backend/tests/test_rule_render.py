"""Rendering a rule tree back into a readable line.

This feeds the systems table's free-text rule columns, which sit next to
hand-written prose for the imported systems. The bar is therefore legibility
rather than completeness: a rendering nobody can scan is no better than the
placeholder it replaced.
"""

from __future__ import annotations

from app.strategy.render import render_condition, render_stop, render_target


def compare(left, cmp, right):
    return {"node": "compare", "left": left, "cmp": cmp, "right": right}


def indicator(name, offset=0):
    return {"op": "indicator", "id": name, "offset": offset}


def price(field="close", offset=0):
    return {"op": "price", "field": field, "offset": offset}


def const(value):
    return {"op": "const", "value": value}


# --------------------------------------------------------------------------- #
# Comparisons
# --------------------------------------------------------------------------- #


def test_a_crossing_reads_as_words_not_as_a_symbol():
    rule = compare(indicator("sma_fast"), "cross_above", indicator("sma_slow"))
    assert render_condition(rule) == "sma_fast crosses above sma_slow"


def test_comparators_use_the_symbols_people_read():
    assert render_condition(compare(price(), ">=", const(100))) == "close ≥ 100"
    assert render_condition(compare(price(), "!=", const(0))) == "close ≠ 0"


def test_an_offset_reads_as_a_bar_index():
    """"one bar ago" would not fit alongside three other terms."""
    rule = compare(price("high", 1), ">", indicator("sma", 2))
    assert render_condition(rule) == "high[1] > sma[2]"


def test_no_offset_means_no_suffix():
    assert render_condition(compare(price(), ">", const(1))) == "close > 1"


def test_a_whole_number_loses_its_decimal_point():
    assert render_condition(compare(price(), ">", const(20.0))) == "close > 20"
    assert render_condition(compare(price(), ">", const(20.5))) == "close > 20.5"


def test_a_parameter_reference_shows_its_name_not_a_value():
    """The definition as authored. Which value it holds today is a property of
    the run, not of the rule."""
    rule = compare(indicator("rsi"), "<", const({"param": "rsi_max"}))
    assert render_condition(rule) == "rsi < $rsi_max"


def test_a_position_operand_reads_as_its_field():
    rule = compare({"op": "position", "field": "bars_held"}, ">", const(48))
    assert render_condition(rule) == "bars_held > 48"


# --------------------------------------------------------------------------- #
# Trees
# --------------------------------------------------------------------------- #


def test_an_all_node_joins_with_and():
    rule = {
        "node": "all",
        "terms": [
            compare(price(), ">", const(100)),
            compare(price(), "<", const(200)),
        ],
    }
    assert render_condition(rule) == "close > 100 and close < 200"


def test_an_any_node_joins_with_or():
    rule = {
        "node": "any",
        "terms": [
            compare(price(), ">", const(100)),
            compare(price(), "<", const(50)),
        ],
    }
    assert render_condition(rule) == "close > 100 or close < 50"


def test_a_nested_or_inside_an_and_is_bracketed():
    """The one case where the flat reading is wrong."""
    rule = {
        "node": "all",
        "terms": [
            compare(indicator("fast"), "cross_above", indicator("slow")),
            {
                "node": "any",
                "terms": [
                    compare(price(), ">", indicator("ema200")),
                    compare(indicator("rsi"), "<", const(30)),
                ],
            },
        ],
    }
    assert render_condition(rule) == (
        "fast crosses above slow and (close > ema200 or rsi < 30)"
    )


def test_same_kind_nesting_is_not_bracketed():
    """``a and b and c`` needs no parentheses, and adding them everywhere would
    make the common case unreadable to disambiguate a case that cannot arise."""
    rule = {
        "node": "all",
        "terms": [
            compare(price(), ">", const(1)),
            {
                "node": "all",
                "terms": [
                    compare(price(), "<", const(2)),
                    compare(price(), "<", const(3)),
                ],
            },
        ],
    }
    assert render_condition(rule) == "close > 1 and close < 2 and close < 3"


def test_a_single_term_group_is_not_bracketed():
    rule = {
        "node": "all",
        "terms": [{"node": "any", "terms": [compare(price(), ">", const(1))]}],
    }
    assert render_condition(rule) == "close > 1"


def test_a_not_node_brackets_its_term():
    rule = {"node": "not", "terms": [compare(price(), ">", const(100))]}
    assert render_condition(rule) == "not (close > 100)"


def test_a_rule_nested_past_readability_is_summarised_honestly():
    """A rule this deep will not be legible on one line however it is rendered;
    truncating and saying so beats emitting a paragraph into a table cell."""
    rule = compare(price(), ">", const(1))
    for _ in range(8):
        rule = {"node": "all", "terms": [rule, compare(price(), "<", const(2))]}

    rendered = render_condition(rule)
    assert "nested conditions" in rendered
    assert len(rendered) < 200


def test_no_rule_renders_as_nothing_rather_than_a_placeholder():
    assert render_condition(None) == ""


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #


def test_an_atr_stop_names_its_indicator():
    assert render_stop({"kind": "atr_multiple", "value": 2.0, "indicator_id": "atr14"}) == (
        "2× atr14"
    )


def test_a_percent_stop_reads_as_a_distance_from_entry():
    assert render_stop({"kind": "percent", "value": 1.5}) == "1.5% from entry"


def test_break_even_and_trailing_are_appended_not_hidden():
    """They change what the stop does; a summary that dropped them would be
    describing a different strategy."""
    rendered = render_stop(
        {
            "kind": "atr_multiple",
            "value": 2.0,
            "indicator_id": "atr14",
            "breakeven_at_r": 1.0,
            "trail_atr_multiple": 3.0,
        }
    )
    assert rendered == "2× atr14 (break-even at 1R, trailing 3× atr14)"


def test_an_r_multiple_target_reads_in_r():
    assert render_target({"kind": "r_multiple", "value": 3.0}) == "3R"


def test_no_target_renders_as_nothing():
    assert render_target(None) == ""


# --------------------------------------------------------------------------- #
# What reaches the systems table
# --------------------------------------------------------------------------- #


def test_the_systems_table_gets_a_real_rule_for_a_declarative_strategy():
    from app.services.strategy_service import _describe_rule, _describe_stop
    from tests.test_strategy_definition import sma_cross

    definition = sma_cross()
    entry = _describe_rule(definition, "entry")

    assert "sma_fast crosses above sma_slow" in entry
    assert "see the strategy definition" not in entry
    assert _describe_stop(definition) == "2× atr14"


def test_a_strategy_without_an_exit_rule_says_so():
    from app.services.strategy_service import _describe_rule
    from tests.test_strategy_definition import sma_cross

    definition = sma_cross(exit_long=None)
    assert _describe_rule(definition, "exit") == "stop and target only"


def test_a_python_strategy_admits_it_cannot_be_rendered():
    """It genuinely cannot, and saying so beats pretending."""
    from app.services.strategy_service import _describe_rule
    from tests.test_strategy_definition import python_strategy

    assert "source" in _describe_rule(python_strategy(), "entry")
