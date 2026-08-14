"""Heuristic concept auto-assignment (Phase 4 T3 + Phase 6 T5, D1/D7).

Pure, DB-free logic: turns a system + the known concepts into assignment
proposals. The API layer persists these with ``source='heuristic'``, stores the
human-readable ``reason`` in ``system_concepts.match_reason`` and never
overwrites manual assignments.

Precedence per concept (at most one proposal per concept):
  1. Prefix ``VP`` -> concept ``Volume Profile`` (NOT the Session variant).
  2. Exact, case-insensitive concept-name match (word-boundary) in any of the
     searched texts (name, entry_rule, sl_rule, tp_rule, notes).
  3. Keyword match from ``KEYWORD_CONCEPT_MAP`` (word-boundary; mandatory for
     short tokens like ``oi``/``poc`` so they never match inside other words).

Special case: a ``session volume profile`` occurrence suppresses the plain
``volume profile`` match at that same position (it belongs to the Session
variant, not to Volume Profile).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol


class _SystemLike(Protocol):
    name: str
    prefix: Optional[str]
    entry_rule: Optional[str]
    sl_rule: Optional[str]
    tp_rule: Optional[str]
    notes: Optional[str]


class _ConceptLike(Protocol):
    id: int
    name: str


@dataclass(frozen=True)
class Proposal:
    concept_id: int
    concept_name: str
    rule: str
    reason: str


VP_PREFIX_RULE = "prefix:VP->Volume Profile"
TEXT_MATCH_RULE = "text-match"
KEYWORD_RULE = "keyword"

_VOLUME_PROFILE_NAME = "Volume Profile"

# Searched fields, in the order that decides which one is reported in ``reason``.
_FIELDS = ("name", "entry_rule", "sl_rule", "tp_rule", "notes")

# Keyword (lowercase) -> concept name (D7). Concept names not present in the DB
# are ignored by the matcher. Order within a concept decides the reported token.
KEYWORD_CONCEPT_MAP: dict[str, str] = {
    "funding": "Funding",
    "open interest": "Open Interest",
    "oi": "Open Interest",
    "order flow": "Order Flow",
    "orderflow": "Order Flow",
    "footprint": "Order Flow",
    "cvd": "Order Flow",
    "volume profile": "Volume Profile",
    "poc": "Volume Profile",
    "vah": "Volume Profile",
    "val": "Volume Profile",
    "hvn": "Volume Profile",
    "lvn": "Volume Profile",
    "session volume profile": "Session Volume Profile",
    "svp": "Session Volume Profile",
    "liquidity": "Liquidity",
    "liquidation": "Liquidity",
    "stop hunt": "Liquidity",
}


def _keywords_for(concept_name: str) -> list[str]:
    """Keywords mapped to a concept, preserving map insertion order."""
    return [kw for kw, name in KEYWORD_CONCEPT_MAP.items() if name == concept_name]


def _iter_fields(system: _SystemLike):
    for field in _FIELDS:
        text = getattr(system, field, None)
        if text:
            yield field, text


def _find_token(token: str, system: _SystemLike, *, suppress_session_vp: bool) -> Optional[str]:
    """Return the first field name containing ``token`` (word-boundary match).

    When ``suppress_session_vp`` is set, occurrences of ``volume profile`` that
    are immediately preceded by ``session`` are skipped (they belong to the
    Session Volume Profile concept).
    """
    pattern = re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE)
    for field, text in _iter_fields(system):
        for match in pattern.finditer(text):
            if suppress_session_vp:
                preceding = text[: match.start()].rstrip().lower()
                if preceding.endswith("session"):
                    continue
            return field
    return None


def _match_concept(system: _SystemLike, concept: _ConceptLike) -> Optional[Proposal]:
    name = concept.name

    # 1. Prefix rule (highest precedence).
    if (system.prefix or "").strip().upper() == "VP" and name == _VOLUME_PROFILE_NAME:
        return Proposal(concept.id, name, VP_PREFIX_RULE, "prefix:VP")

    is_vp = name == _VOLUME_PROFILE_NAME

    # 2. Exact concept-name match (word-boundary).
    field = _find_token(name, system, suppress_session_vp=is_vp)
    if field is not None:
        return Proposal(concept.id, name, TEXT_MATCH_RULE, f"name:'{name}' in {field}")

    # 3. Keyword match.
    for keyword in _keywords_for(name):
        suppress = is_vp and keyword == "volume profile"
        field = _find_token(keyword, system, suppress_session_vp=suppress)
        if field is not None:
            return Proposal(
                concept.id, name, KEYWORD_RULE, f"keyword:'{keyword}' in {field}"
            )

    return None


def propose_assignments(
    system: _SystemLike, concepts: list[_ConceptLike]
) -> list[Proposal]:
    """Return at most one concept proposal per concept for a single system."""
    proposals: list[Proposal] = []
    for concept in concepts:
        proposal = _match_concept(system, concept)
        if proposal is not None:
            proposals.append(proposal)
    return proposals
