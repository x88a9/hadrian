"""Unit tests for the DB-free concept auto-assignment heuristics (T3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.concept_assign import (
    KEYWORD_RULE,
    TEXT_MATCH_RULE,
    VP_PREFIX_RULE,
    propose_assignments,
)


@dataclass
class FakeSystem:
    name: str
    prefix: Optional[str] = None
    entry_rule: Optional[str] = None
    sl_rule: Optional[str] = None
    tp_rule: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class FakeConcept:
    id: int
    name: str


CONCEPTS = [
    FakeConcept(1, "Open Interest"),
    FakeConcept(2, "Funding"),
    FakeConcept(3, "Session Volume Profile"),
    FakeConcept(4, "Order Flow"),
    FakeConcept(5, "Liquidity"),
    FakeConcept(6, "Volume Profile"),
]


def test_vp_prefix_assigns_volume_profile_only():
    system = FakeSystem(name="VP-M5-001", prefix="VP")
    props = propose_assignments(system, CONCEPTS)
    assert len(props) == 1
    p = props[0]
    assert p.concept_name == "Volume Profile"
    assert p.concept_id == 6
    assert p.rule == VP_PREFIX_RULE


def test_vp_prefix_case_insensitive():
    system = FakeSystem(name="vp-m5-001", prefix="vp")
    props = propose_assignments(system, CONCEPTS)
    assert [p.concept_name for p in props] == ["Volume Profile"]


def test_text_match_in_rules_case_insensitive():
    system = FakeSystem(
        name="B-H1-801",
        prefix="B",
        entry_rule="Enter on break above the funding-driven imbalance",
        sl_rule="below the liquidity pool",
    )
    props = propose_assignments(system, CONCEPTS)
    names = {p.concept_name for p in props}
    assert names == {"Funding", "Liquidity"}
    assert all(p.rule == TEXT_MATCH_RULE for p in props)


def test_no_match_returns_empty():
    system = FakeSystem(name="B-H1-802", prefix="B", entry_rule="simple breakout")
    assert propose_assignments(system, CONCEPTS) == []


def test_prefix_rule_wins_over_text_for_same_concept():
    system = FakeSystem(
        name="VP-M5-002",
        prefix="VP",
        entry_rule="uses the volume profile POC",
    )
    props = propose_assignments(system, CONCEPTS)
    vp = [p for p in props if p.concept_name == "Volume Profile"]
    assert len(vp) == 1
    assert vp[0].rule == VP_PREFIX_RULE


def test_no_duplicate_proposals_per_concept():
    system = FakeSystem(
        name="B-H1-803",
        prefix="B",
        entry_rule="funding funding funding",
        notes="funding again",
    )
    props = propose_assignments(system, CONCEPTS)
    assert len([p for p in props if p.concept_name == "Funding"]) == 1


# --------------------------------------------------------------------------- #
# Phase 6, T5: keyword heuristic + reason strings
# --------------------------------------------------------------------------- #
def _by_name(props, name):
    return next(p for p in props if p.concept_name == name)


def test_keyword_match_per_field_reasons():
    system = FakeSystem(
        name="B-H1-010",
        prefix="B",
        entry_rule="enter on high oi build-up",
        sl_rule="below the poc",
        tp_rule="target the cvd flip",
    )
    props = propose_assignments(system, CONCEPTS)
    names = {p.concept_name for p in props}
    assert {"Open Interest", "Volume Profile", "Order Flow"} <= names

    oi = _by_name(props, "Open Interest")
    assert oi.rule == KEYWORD_RULE
    assert oi.reason == "keyword:'oi' in entry_rule"

    vp = _by_name(props, "Volume Profile")
    assert vp.reason == "keyword:'poc' in sl_rule"

    of = _by_name(props, "Order Flow")
    assert of.reason == "keyword:'cvd' in tp_rule"


def test_exact_name_reason_and_field():
    system = FakeSystem(name="B-H1-011", prefix="B", notes="uses Funding rate skew")
    props = propose_assignments(system, CONCEPTS)
    funding = _by_name(props, "Funding")
    assert funding.rule == TEXT_MATCH_RULE
    assert funding.reason == "name:'Funding' in notes"


def test_word_boundary_no_false_positive_for_short_tokens():
    # "point" contains "oi" but must not match the 'oi' keyword.
    system = FakeSystem(
        name="B-H1-012", prefix="B", entry_rule="enter at the pivot point"
    )
    props = propose_assignments(system, CONCEPTS)
    assert all(p.concept_name != "Open Interest" for p in props)


def test_session_volume_profile_suppresses_plain_volume_profile():
    system = FakeSystem(
        name="B-H1-013",
        prefix="B",
        entry_rule="trade the session volume profile value area",
    )
    props = propose_assignments(system, CONCEPTS)
    names = {p.concept_name for p in props}
    assert "Session Volume Profile" in names
    assert "Volume Profile" not in names


def test_plain_volume_profile_still_matches_when_standalone():
    system = FakeSystem(
        name="B-H1-014",
        prefix="B",
        entry_rule="the session opens; later trade the volume profile poc",
    )
    props = propose_assignments(system, CONCEPTS)
    names = {p.concept_name for p in props}
    assert "Volume Profile" in names


def test_prefix_precedence_over_name_and_keyword():
    system = FakeSystem(
        name="VP-M5-003", prefix="VP", entry_rule="volume profile poc touch"
    )
    props = propose_assignments(system, CONCEPTS)
    vp = _by_name(props, "Volume Profile")
    assert vp.rule == VP_PREFIX_RULE
    assert vp.reason == "prefix:VP"


def test_name_precedence_over_keyword():
    # "open interest" is both the exact concept name and covered by keywords;
    # the exact-name match wins and reports a name-reason.
    system = FakeSystem(
        name="B-H1-015", prefix="B", entry_rule="fade the open interest spike"
    )
    props = propose_assignments(system, CONCEPTS)
    oi = _by_name(props, "Open Interest")
    assert oi.rule == TEXT_MATCH_RULE
    assert oi.reason == "name:'Open Interest' in entry_rule"
