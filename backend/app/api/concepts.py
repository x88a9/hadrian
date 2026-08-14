"""REST endpoints for concepts, system<->concept assignments and the graph
(Phase 4, T2/T3).

``GET /concepts/graph`` is registered before any dynamic ``/concepts/{...}``
route; there is deliberately no ``GET /concepts/{id}`` route, so ``graph`` and
``auto-assign`` can never be shadowed by a path parameter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Concept, System, SystemConcept
from app.schemas.concept import (
    AutoAssignItem,
    AutoAssignResponse,
    ConceptCreate,
    ConceptOut,
    ConceptsResponse,
    GraphLink,
    GraphNode,
    GraphResponse,
    SystemConceptCreate,
    SystemConceptItem,
    SystemConceptsResponse,
)
from app.services.concept_assign import propose_assignments

router = APIRouter(tags=["concepts"])


def _concept_out(concept: Concept, system_count: int) -> ConceptOut:
    return ConceptOut(
        id=concept.id,
        name=concept.name,
        description=concept.description,
        system_count=system_count,
    )


@router.get("/concepts", response_model=ConceptsResponse)
def list_concepts(db: Session = Depends(get_db)) -> ConceptsResponse:
    counts = dict(
        db.execute(
            select(SystemConcept.concept_id, func.count(SystemConcept.id)).group_by(
                SystemConcept.concept_id
            )
        ).all()
    )
    concepts = db.execute(select(Concept).order_by(Concept.name)).scalars().all()
    items = [_concept_out(c, counts.get(c.id, 0)) for c in concepts]
    return ConceptsResponse(items=items)


@router.post("/concepts", response_model=ConceptOut)
def upsert_concept(
    body: ConceptCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> ConceptOut:
    """Upsert a concept by name (201 new, 200 existing)."""
    existing = db.execute(
        select(Concept).where(Concept.name == body.name)
    ).scalar_one_or_none()

    if existing is None:
        concept = Concept(name=body.name, description=body.description)
        db.add(concept)
        db.commit()
        db.refresh(concept)
        response.status_code = 201
        return _concept_out(concept, 0)

    if body.description is not None:
        existing.description = body.description
        db.commit()
        db.refresh(existing)
    count = db.execute(
        select(func.count(SystemConcept.id)).where(
            SystemConcept.concept_id == existing.id
        )
    ).scalar_one()
    response.status_code = 200
    return _concept_out(existing, count)


@router.get("/concepts/graph", response_model=GraphResponse)
def concept_graph(
    include_unlinked_systems: bool = Query(False),
    db: Session = Depends(get_db),
) -> GraphResponse:
    concepts = db.execute(select(Concept).order_by(Concept.id)).scalars().all()
    links_rows = db.execute(select(SystemConcept)).scalars().all()
    systems = db.execute(select(System).order_by(System.id)).scalars().all()

    linked_system_ids = {link.system_id for link in links_rows}

    nodes: list[GraphNode] = []
    for concept in concepts:
        nodes.append(
            GraphNode(
                id=f"concept:{concept.id}",
                type="concept",
                label=concept.name,
            )
        )
    for system in systems:
        if not include_unlinked_systems and system.id not in linked_system_ids:
            continue
        nodes.append(
            GraphNode(
                id=f"system:{system.id}",
                type="system",
                label=system.name,
                status=system.status,
                import_status=system.import_status,
            )
        )

    links = [
        GraphLink(
            source=f"system:{link.system_id}",
            target=f"concept:{link.concept_id}",
            assignment_source=link.source,
        )
        for link in links_rows
    ]
    return GraphResponse(nodes=nodes, links=links)


@router.post("/concepts/auto-assign", response_model=AutoAssignResponse)
def auto_assign_concepts(
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
) -> AutoAssignResponse:
    """Apply the heuristic rules to every system (source='heuristic').

    Idempotent: existing assignments (manual OR heuristic) are kept and never
    duplicated; a second call creates nothing.

    ``dry_run=true`` (Phase 6, T13) computes the very same proposals but
    persists nothing. Existing pairs are skipped exactly as in the real run, so
    the preview only ever lists genuinely new suggestions (status='proposed').
    ``created`` is then 0 (nothing was written).
    """
    concepts = db.execute(select(Concept)).scalars().all()
    systems = db.execute(select(System)).scalars().all()

    existing_pairs = {
        (link.system_id, link.concept_id)
        for link in db.execute(select(SystemConcept)).scalars().all()
    }

    created = 0
    skipped = 0
    assignments: list[AutoAssignItem] = []
    for system in systems:
        for proposal in propose_assignments(system, concepts):
            pair = (system.id, proposal.concept_id)
            if pair in existing_pairs:
                skipped += 1
                continue
            if not dry_run:
                db.add(
                    SystemConcept(
                        system_id=system.id,
                        concept_id=proposal.concept_id,
                        source="heuristic",
                        match_reason=proposal.reason,
                    )
                )
                created += 1
            existing_pairs.add(pair)
            assignments.append(
                AutoAssignItem(
                    system=system.name,
                    concept=proposal.concept_name,
                    rule=proposal.rule,
                    reason=proposal.reason,
                    system_id=system.id,
                    concept_id=proposal.concept_id,
                    status="proposed" if dry_run else "created",
                )
            )
    if not dry_run:
        db.commit()
    return AutoAssignResponse(
        created=created, skipped_existing=skipped, assignments=assignments
    )


@router.get("/systems/{system_id}/concepts", response_model=SystemConceptsResponse)
def list_system_concepts(
    system_id: int, db: Session = Depends(get_db)
) -> SystemConceptsResponse:
    """List the concepts assigned to a system with source + match reason (T5)."""
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail=f"system {system_id} not found")

    rows = db.execute(
        select(SystemConcept, Concept)
        .join(Concept, Concept.id == SystemConcept.concept_id)
        .where(SystemConcept.system_id == system_id)
        .order_by(Concept.name)
    ).all()

    items = [
        SystemConceptItem(
            concept_id=concept.id,
            name=concept.name,
            description=concept.description,
            source=link.source,
            match_reason=link.match_reason,
            created_at=link.created_at,
        )
        for link, concept in rows
    ]
    return SystemConceptsResponse(items=items)


@router.post("/systems/{system_id}/concepts", response_model=ConceptOut)
def assign_concept(
    system_id: int,
    body: SystemConceptCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> ConceptOut:
    """Assign a concept to a system. 201 new, 200 existing.

    ``source`` defaults to ``'manual'`` (plain assign). Confirming a heuristic
    proposal from the auto-assign preview (Phase 6, T13) passes
    ``source='heuristic'`` plus its ``match_reason`` so the edge keeps its
    heuristic provenance instead of masquerading as a manual assignment.
    """
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail=f"system {system_id} not found")
    concept = db.get(Concept, body.concept_id)
    if concept is None:
        raise HTTPException(
            status_code=404, detail=f"concept {body.concept_id} not found"
        )

    existing = db.execute(
        select(SystemConcept).where(
            SystemConcept.system_id == system_id,
            SystemConcept.concept_id == body.concept_id,
        )
    ).scalar_one_or_none()

    if existing is None:
        db.add(
            SystemConcept(
                system_id=system_id,
                concept_id=body.concept_id,
                source=body.source,
                match_reason=body.match_reason if body.source == "heuristic" else None,
            )
        )
        db.commit()
        response.status_code = 201
    else:
        response.status_code = 200

    count = db.execute(
        select(func.count(SystemConcept.id)).where(
            SystemConcept.concept_id == body.concept_id
        )
    ).scalar_one()
    return _concept_out(concept, count)


@router.delete("/systems/{system_id}/concepts/{concept_id}", status_code=204)
def unassign_concept(
    system_id: int,
    concept_id: int,
    db: Session = Depends(get_db),
) -> Response:
    link = db.execute(
        select(SystemConcept).where(
            SystemConcept.system_id == system_id,
            SystemConcept.concept_id == concept_id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=404,
            detail=f"assignment system={system_id} concept={concept_id} not found",
        )
    db.delete(link)
    db.commit()
    return Response(status_code=204)
