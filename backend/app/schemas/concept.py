"""Pydantic schemas for the /concepts endpoints (Phase 4, T2/T3; Phase 6, T5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class ConceptOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    system_count: int


class ConceptsResponse(BaseModel):
    items: list[ConceptOut]


class ConceptCreate(BaseModel):
    name: str
    description: Optional[str] = None


class SystemConceptCreate(BaseModel):
    concept_id: int
    # Phase 6, T13: optional provenance for confirmed heuristic proposals.
    # Default 'manual' keeps the plain assign endpoint backward compatible.
    source: Literal["manual", "heuristic"] = "manual"
    match_reason: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    type: Literal["concept", "system"]
    label: str
    status: Optional[str] = None
    import_status: Optional[str] = None


class GraphLink(BaseModel):
    source: str
    target: str
    assignment_source: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]


class AutoAssignItem(BaseModel):
    system: str
    concept: str
    rule: str
    # Human-readable match reason (Phase 6, D6/D7), also stored in match_reason.
    reason: Optional[str] = None
    # Phase 6, T13: IDs so the preview UI can confirm a single proposal, and a
    # status distinguishing persisted rows ('created') from a dry-run preview
    # ('proposed'). Additive; default 'created' preserves the non-dry-run shape.
    system_id: Optional[int] = None
    concept_id: Optional[int] = None
    status: str = "created"


class AutoAssignResponse(BaseModel):
    created: int
    skipped_existing: int
    assignments: list[AutoAssignItem]


class SystemConceptItem(BaseModel):
    """One concept assigned to a system (Phase 6, T5)."""

    concept_id: int
    name: str
    description: Optional[str] = None
    source: str
    match_reason: Optional[str] = None
    created_at: datetime


class SystemConceptsResponse(BaseModel):
    items: list[SystemConceptItem]
