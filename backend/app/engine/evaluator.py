"""Evaluating the declarative rule tree.

Works on the definition's plain-dict form rather than the pydantic models, for
the same reason as the rest of this package: everything in ``app/engine`` has
to be able to run inside the sandbox, and the definition has already been
validated by the time it gets here. Validation belongs at the boundary; this
module's job is to be fast and literal about what the tree says.

Two rules govern everything below.

**A missing value is false, not an error.** An indicator that has not warmed up
yet returns ``None``, and any comparison involving one is false. That is what
lets a strategy's first hundred bars pass without ceremony, and it means a
warm-up period can never produce a signal by accident.

**Offsets only ever look backwards.** The schema refuses a negative offset, and
this module resolves ``i - offset`` and returns ``None`` below zero rather than
wrapping round to the end of the series — which is what negative indexing would
have done, silently, and would have been a lookahead bug of the worst kind:
correct-looking, occasional, and profitable.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

__all__ = ["EvaluationError", "build_signal_fn", "evaluate_condition"]


class EvaluationError(ValueError):
    """The rule tree contains something this evaluator does not implement."""


class _Signal:
    """Minimal stand-in for ``interface.Signal``.

    The engine only reads ``action``, ``stop_price`` and ``tag``, and importing
    the real class here would tie the declarative path to the authoring module
    it has nothing else to do with.
    """

    __slots__ = ("action", "stop_price", "tag")

    def __init__(self, action: str, stop_price: float | None = None, tag: str | None = None):
        self.action = action
        self.stop_price = stop_price
        self.tag = tag


def _operand_value(
    operand: Mapping[str, Any],
    bars: Mapping[str, Sequence],
    indicators: Mapping[str, Sequence[float | None]],
    index: int,
    position: Any,
) -> float | None:
    kind = operand.get("op")

    if kind == "const":
        return float(operand["value"])

    if kind == "price":
        target = index - int(operand.get("offset", 0))
        if target < 0:
            return None
        series = bars.get(operand.get("field", "close"))
        if series is None:
            raise EvaluationError(f"unknown price field {operand.get('field')!r}")
        return float(series[target])

    if kind == "indicator":
        target = index - int(operand.get("offset", 0))
        if target < 0:
            return None
        try:
            series = indicators[operand["id"]]
        except KeyError:
            raise EvaluationError(
                f"rule references undeclared indicator {operand.get('id')!r}"
            ) from None
        value = series[target]
        return None if value is None else float(value)

    if kind == "position":
        if position is None:
            # Flat: a comparison against position state is false rather than an
            # error, so an exit rule simply never fires while there is nothing
            # to exit.
            return None
        field = operand.get("field")
        if field == "bars_held":
            return float(index - position.entry_index)
        if field == "unrealised_r":
            close = bars["close"][index]
            return float(position.unrealised_r(close))
        if field == "entry_price":
            return float(position.entry_price)
        if field == "direction_sign":
            return float(position.sign)
        raise EvaluationError(f"unknown position field {field!r}")

    raise EvaluationError(f"unknown operand kind {kind!r}")


_COMPARATORS: dict[str, Callable[[float, float], bool]] = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate_condition(
    condition: Mapping[str, Any] | None,
    bars: Mapping[str, Sequence],
    indicators: Mapping[str, Sequence[float | None]],
    index: int,
    position: Any = None,
) -> bool:
    """True when the condition holds at bar ``index``.

    ``None`` is true, so that an absent exit rule does not have to be
    special-cased by every caller — an absent *entry* rule is refused by the
    schema, so there is no risk of "no rule" meaning "always enter".
    """
    if condition is None:
        return True

    node = condition.get("node")

    if node == "all":
        return all(
            evaluate_condition(t, bars, indicators, index, position)
            for t in condition["terms"]
        )
    if node == "any":
        return any(
            evaluate_condition(t, bars, indicators, index, position)
            for t in condition["terms"]
        )
    if node == "not":
        return not evaluate_condition(
            condition["terms"][0], bars, indicators, index, position
        )

    if node != "compare":
        raise EvaluationError(f"unknown node kind {node!r}")

    comparator = condition["cmp"]
    left = condition["left"]
    right = condition["right"]

    if comparator in ("cross_above", "cross_below"):
        if index < 1:
            return False
        now_left = _operand_value(left, bars, indicators, index, position)
        now_right = _operand_value(right, bars, indicators, index, position)
        was_left = _operand_value(left, bars, indicators, index - 1, position)
        was_right = _operand_value(right, bars, indicators, index - 1, position)
        if None in (now_left, now_right, was_left, was_right):
            return False
        if comparator == "cross_above":
            return was_left <= was_right and now_left > now_right
        return was_left >= was_right and now_left < now_right

    a = _operand_value(left, bars, indicators, index, position)
    b = _operand_value(right, bars, indicators, index, position)
    if a is None or b is None:
        return False
    try:
        return _COMPARATORS[comparator](a, b)
    except KeyError:
        raise EvaluationError(f"unknown comparator {comparator!r}") from None


def build_signal_fn(
    definition: Mapping[str, Any],
    bars: Mapping[str, Sequence],
    indicators: Mapping[str, Sequence[float | None]],
) -> Callable[[int, Any], Any]:
    """Reduce a declarative definition to the callback the engine drives.

    This is the seam that lets one engine serve both authoring paths: a
    sandboxed Python strategy produces a callback of exactly this shape, so any
    difference between a designed strategy and a written one comes from the
    rules and never from the machinery underneath them.
    """
    entry_long = definition.get("entry_long")
    entry_short = definition.get("entry_short")
    exit_long = definition.get("exit_long")
    exit_short = definition.get("exit_short")
    filters = definition.get("filters") or []

    def signal_fn(index: int, position: Any) -> Any:
        if position is not None:
            rule = exit_long if position.direction == "long" else exit_short
            if rule is not None and evaluate_condition(
                rule, bars, indicators, index, position
            ):
                return _Signal("exit")
            return None

        # Filters gate entries only. An open position is managed by its exit
        # rule and its stop; a filter turning false mid-trade should not eject
        # a position the exit rule has not asked to close.
        if not all(
            evaluate_condition(f, bars, indicators, index, None) for f in filters
        ):
            return None

        if entry_long is not None and evaluate_condition(
            entry_long, bars, indicators, index, None
        ):
            return _Signal("enter_long")
        if entry_short is not None and evaluate_condition(
            entry_short, bars, indicators, index, None
        ):
            return _Signal("enter_short")
        return None

    return signal_fn
