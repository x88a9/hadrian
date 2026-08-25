"""Rendering a rule tree back into something a person reads.

The ``systems`` table's ``entry_rule`` / ``sl_rule`` / ``tp_rule`` columns hold
prose, written by hand for the imported systems. An engine system has a
machine-readable definition instead, and until now it filled those columns with
a placeholder pointing at the definition — which is accurate and useless: the
systems list shows those columns side by side, and one row saying "see the
strategy definition" next to fifty rows describing themselves is a hole in the
table.

So this renders the tree. Not a full pretty-printer — the block designer is
where a rule is *read* in detail — but a one-line summary faithful enough that
the list is worth scanning:

    sma_fast crosses above sma_slow and close > ema200

Parentheses appear only where precedence would otherwise be ambiguous. A
rendering that bracketed every term would be unambiguous and unreadable, and
the point of this is to be read.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["render_condition", "render_stop", "render_target"]

_COMPARATOR_WORDS = {
    "<": "<",
    "<=": "≤",
    ">": ">",
    ">=": "≥",
    "==": "=",
    "!=": "≠",
    "cross_above": "crosses above",
    "cross_below": "crosses below",
}

#: How deep to go before giving up and summarising. A rule nested past this is
#: not going to be legible on one line however it is rendered, and truncating
#: honestly beats emitting a paragraph into a table cell.
_MAX_DEPTH = 4


def render_condition(condition: Mapping[str, Any] | None, depth: int = 0) -> str:
    """One line describing ``condition``. Empty string for ``None``."""
    if condition is None:
        return ""

    node = condition.get("node")

    if node == "compare":
        left = _render_operand(condition.get("left"))
        right = _render_operand(condition.get("right"))
        comparator = _COMPARATOR_WORDS.get(condition.get("cmp", ""), condition.get("cmp", "?"))
        return f"{left} {comparator} {right}"

    if node in ("all", "any"):
        terms = condition.get("terms") or []
        if depth >= _MAX_DEPTH:
            return f"({len(terms)} nested conditions)"
        joiner = " and " if node == "all" else " or "
        rendered = [_maybe_parenthesise(t, node, depth + 1) for t in terms]
        return joiner.join(r for r in rendered if r)

    if node == "not":
        terms = condition.get("terms") or []
        if not terms:
            return ""
        inner = render_condition(terms[0], depth + 1)
        return f"not ({inner})" if inner else ""

    return "?"


def _maybe_parenthesise(term: Mapping[str, Any], parent: str, depth: int) -> str:
    """Bracket a term only when the parent's joiner would misread without it.

    ``a and b and c`` needs none; ``a and (b or c)`` does. Mixing ``and`` into
    an ``or`` is the only case where the flat reading is wrong.
    """
    rendered = render_condition(term, depth)
    if not rendered:
        return ""
    child = term.get("node")
    if child in ("all", "any") and child != parent and len(term.get("terms") or []) > 1:
        return f"({rendered})"
    return rendered


def _render_operand(operand: Mapping[str, Any] | None) -> str:
    if not operand:
        return "?"

    kind = operand.get("op")
    offset = int(operand.get("offset", 0) or 0)
    # "[1]" reads as "one bar back", which is what an offset is. Spelling it
    # out ("close one bar ago") would not fit alongside three other terms.
    suffix = f"[{offset}]" if offset else ""

    if kind == "price":
        return f"{operand.get('field', 'close')}{suffix}"
    if kind == "indicator":
        return f"{operand.get('id', '?')}{suffix}"
    if kind == "position":
        return str(operand.get("field", "?"))
    if kind == "const":
        return _render_number(operand.get("value"))
    return "?"


def _render_number(value: Any) -> str:
    """A number, a parameter reference, or an honest question mark."""
    if isinstance(value, Mapping):
        # An unresolved {"param": "fast"} — the definition as authored, before
        # a run substitutes it. Showing the name is more useful than the value
        # it happens to hold today.
        name = value.get("param")
        return f"${name}" if name else "?"
    if isinstance(value, bool) or value is None:
        return "?"
    if isinstance(value, (int, float)):
        # Trim a float that is really an integer: "20" not "20.0".
        return str(int(value)) if float(value).is_integer() else f"{value:g}"
    return str(value)


def render_stop(stop: Mapping[str, Any] | None) -> str:
    """The stop, as one phrase. This defines 1R, so it is never absent."""
    if not stop:
        return ""
    kind = stop.get("kind")
    value = _render_number(stop.get("value"))
    indicator = stop.get("indicator_id")

    if kind == "atr_multiple":
        base = f"{value}× {indicator}"
    elif kind == "percent":
        base = f"{value}% from entry"
    elif kind == "fixed_points":
        base = f"{value} points from entry"
    elif kind == "indicator":
        base = f"at {indicator}"
    else:
        base = str(kind)

    extras = []
    if stop.get("breakeven_at_r") is not None:
        extras.append(f"break-even at {_render_number(stop['breakeven_at_r'])}R")
    if stop.get("trail_atr_multiple") is not None:
        extras.append(f"trailing {_render_number(stop['trail_atr_multiple'])}× {indicator}")
    return f"{base} ({', '.join(extras)})" if extras else base


def render_target(target: Mapping[str, Any] | None) -> str:
    """The target, or an empty string when the strategy has none."""
    if not target:
        return ""
    kind = target.get("kind")
    value = _render_number(target.get("value"))
    if kind == "r_multiple":
        return f"{value}R"
    if kind == "percent":
        return f"{value}% from entry"
    if kind == "indicator":
        return f"at {target.get('indicator_id')}"
    return str(kind)
