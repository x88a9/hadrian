"""The rule vocabulary, read off the schema rather than written down twice.

The block designer needs to know what an indicator can be, which comparators
exist, what a stop can key on. All of that is already stated in
``definition.py`` as ``Literal`` types and in ``indicators.py`` as a registry —
so this module reads those, rather than repeating them in a form that would
quietly drift the first time someone adds an indicator.

Nothing here is a second source of truth. Every list is derived, and the tests
assert that the derivation still covers what the schema allows: a new indicator
kind with no metadata fails, and metadata for a kind the engine cannot compute
fails too.
"""

from __future__ import annotations

import typing
from typing import Any

from app.data.candles import TIMEFRAMES
from app.engine.indicators import INDICATOR_META, INDICATORS
from app.strategy.definition import (
    CROSSING,
    SCHEMA_VERSION,
    Comparator,
    CostSpec,
    IndicatorKind,
    PositionOperand,
    PriceField,
    StopSpec,
    StrategyDefinition,
    TargetSpec,
)

__all__ = ["rule_vocabulary"]


def _args(annotation: Any) -> list[str]:
    return list(typing.get_args(annotation))


def _literal_of(model: type, field: str) -> list[str]:
    """The allowed values of a model field declared as a ``Literal``."""
    return _args(model.model_fields[field].annotation)


#: Comparators that need an indicator on at least one side to mean anything,
#: and the ones that read naturally against a bare number. Presentational only:
#: the schema accepts any operand on either side, and this just decides what the
#: designer offers first.
_NUMERIC_FRIENDLY = ("<", "<=", ">", ">=", "==", "!=")


def rule_vocabulary() -> dict:
    """Everything a designer needs to build a valid declarative definition."""
    stop_kinds = _literal_of(StopSpec, "kind")
    target_kinds = _literal_of(TargetSpec, "kind")

    return {
        "schema_version": SCHEMA_VERSION,
        "price_fields": _args(PriceField),
        "timeframes": sorted(TIMEFRAMES, key=lambda tf: TIMEFRAMES[tf]),
        "directions": _literal_of(StrategyDefinition, "direction"),
        "rule_carriers": _literal_of(StrategyDefinition, "rules"),
        "indicators": [
            {
                "kind": kind,
                "label": INDICATOR_META[kind]["label"],
                "uses_source": INDICATOR_META[kind]["uses_source"],
                "params": INDICATOR_META[kind]["params"],
            }
            # Ordered by the schema's own Literal, so the designer's list and
            # the type that validates it are in the same order.
            for kind in _args(IndicatorKind)
        ],
        "comparators": [
            {
                "op": op,
                # A crossing compares a bar with the one before it, so the
                # schema refuses an offset on either side of one.
                "is_crossing": op in CROSSING,
                "allows_offset": op not in CROSSING,
                "numeric_friendly": op in _NUMERIC_FRIENDLY,
            }
            for op in _args(Comparator)
        ],
        "operand_kinds": ["price", "indicator", "const", "position"],
        "position_fields": _literal_of(PositionOperand, "field"),
        # Where a position operand may be used at all. Entry rules and filters
        # are evaluated while flat, so the schema refuses one there — the
        # designer should not offer it rather than let the user find out on
        # save. See definition._reject_position_operands.
        "position_operand_slots": ["exit_long", "exit_short"],
        "rule_slots": [
            {"slot": "entry_long", "label": "Einstieg long", "allows_position": False},
            {"slot": "entry_short", "label": "Einstieg short", "allows_position": False},
            {"slot": "exit_long", "label": "Ausstieg long", "allows_position": True},
            {"slot": "exit_short", "label": "Ausstieg short", "allows_position": True},
            {"slot": "filters", "label": "Filter", "allows_position": False},
        ],
        "bool_nodes": [
            {"node": "all", "label": "All of", "arity": "many"},
            {"node": "any", "label": "Any of", "arity": "many"},
            {"node": "not", "label": "Not", "arity": "one"},
        ],
        "stop_kinds": [
            {"kind": kind, "requires_indicator": kind in ("atr_multiple", "indicator")}
            for kind in stop_kinds
        ],
        "target_kinds": [
            {"kind": kind, "requires_indicator": kind == "indicator"}
            for kind in target_kinds
        ],
        "cost_defaults": CostSpec().model_dump(mode="json"),
    }
