"""Integration tests for the concepts API + graph + auto-assign (T2/T3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import Concept, System, SystemConcept

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def seed_concepts(db_session):
    """Seed the 6 concepts (mirrors migration 0003) and two systems."""
    names = [
        "Open Interest",
        "Funding",
        "Session Volume Profile",
        "Order Flow",
        "Liquidity",
        "Volume Profile",
    ]
    concepts = [Concept(name=n) for n in names]
    sys_vp = System(
        name="VP-M5-001",
        prefix="VP",
        timeframe="M5",
        status="backtest",
        import_status="complete",
        entry_rule="volume profile POC touch",
    )
    sys_b = System(
        name="B-H1-801",
        prefix="B",
        timeframe="H1",
        status="active",
        import_status="complete",
        entry_rule="break above funding imbalance",
    )
    db_session.add_all(concepts + [sys_vp, sys_b])
    db_session.commit()
    return {
        "concepts": {c.name: c.id for c in concepts},
        "sys_vp": sys_vp.id,
        "sys_b": sys_b.id,
    }


def test_list_concepts(client, seed_concepts):
    r = client.get("/concepts")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 6
    assert all(item["system_count"] == 0 for item in items)
    # sorted by name
    assert items[0]["name"] == "Funding"


def test_upsert_concept_create_then_update(client, seed_concepts):
    r = client.post("/concepts", json={"name": "New Concept", "description": "x"})
    assert r.status_code == 201
    assert r.json()["name"] == "New Concept"

    r2 = client.post(
        "/concepts", json={"name": "New Concept", "description": "updated"}
    )
    assert r2.status_code == 200
    assert r2.json()["description"] == "updated"


def test_assign_and_unassign_roundtrip(client, seed_concepts):
    sid = seed_concepts["sys_vp"]
    cid = seed_concepts["concepts"]["Volume Profile"]

    r = client.post(f"/systems/{sid}/concepts", json={"concept_id": cid})
    assert r.status_code == 201
    assert r.json()["system_count"] == 1

    # Double-assign does not duplicate -> 200.
    r2 = client.post(f"/systems/{sid}/concepts", json={"concept_id": cid})
    assert r2.status_code == 200
    assert r2.json()["system_count"] == 1

    d = client.delete(f"/systems/{sid}/concepts/{cid}")
    assert d.status_code == 204

    d2 = client.delete(f"/systems/{sid}/concepts/{cid}")
    assert d2.status_code == 404


def test_assign_unknown_system_or_concept(client, seed_concepts):
    cid = seed_concepts["concepts"]["Funding"]
    assert client.post("/systems/99999/concepts", json={"concept_id": cid}).status_code == 404

    sid = seed_concepts["sys_b"]
    assert client.post(f"/systems/{sid}/concepts", json={"concept_id": 99999}).status_code == 404


def test_graph_zero_edges_valid(client, seed_concepts):
    r = client.get("/concepts/graph")
    assert r.status_code == 200
    body = r.json()
    # Only concept nodes (no linked systems), zero links.
    assert len(body["links"]) == 0
    assert all(n["type"] == "concept" for n in body["nodes"])
    assert len(body["nodes"]) == 6


def test_graph_include_unlinked_systems(client, seed_concepts):
    r = client.get("/concepts/graph", params={"include_unlinked_systems": "true"})
    body = r.json()
    system_nodes = [n for n in body["nodes"] if n["type"] == "system"]
    assert len(system_nodes) == 2
    assert system_nodes[0]["status"] in {"backtest", "active"}


def test_graph_after_two_assignments(client, seed_concepts):
    sid_vp = seed_concepts["sys_vp"]
    sid_b = seed_concepts["sys_b"]
    cid_vp = seed_concepts["concepts"]["Volume Profile"]
    cid_fund = seed_concepts["concepts"]["Funding"]

    client.post(f"/systems/{sid_vp}/concepts", json={"concept_id": cid_vp})
    client.post(f"/systems/{sid_b}/concepts", json={"concept_id": cid_fund})

    body = client.get("/concepts/graph").json()
    assert len(body["links"]) == 2
    for link in body["links"]:
        assert link["source"].startswith("system:")
        assert link["target"].startswith("concept:")
        assert link["assignment_source"] == "manual"
    # Both linked systems appear as nodes.
    system_nodes = {n["id"] for n in body["nodes"] if n["type"] == "system"}
    assert system_nodes == {f"system:{sid_vp}", f"system:{sid_b}"}


def test_auto_assign_vp_and_text_match(client, seed_concepts):
    r = client.post("/concepts/auto-assign")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] > 0
    pairs = {(a["system"], a["concept"]) for a in body["assignments"]}
    # VP prefix rule
    assert ("VP-M5-001", "Volume Profile") in pairs
    # text-match rule on funding
    assert ("B-H1-801", "Funding") in pairs

    # Second call is idempotent.
    r2 = client.post("/concepts/auto-assign")
    assert r2.json()["created"] == 0
    assert r2.json()["skipped_existing"] >= body["created"]


def test_auto_assign_keeps_manual(client, seed_concepts):
    sid_vp = seed_concepts["sys_vp"]
    cid_vp = seed_concepts["concepts"]["Volume Profile"]
    client.post(f"/systems/{sid_vp}/concepts", json={"concept_id": cid_vp})

    client.post("/concepts/auto-assign")

    body = client.get("/concepts/graph").json()
    vp_link = next(
        link
        for link in body["links"]
        if link["source"] == f"system:{sid_vp}"
        and link["target"] == f"concept:{cid_vp}"
    )
    assert vp_link["assignment_source"] == "manual"


# --------------------------------------------------------------------------- #
# Phase 6, T5: GET /systems/{id}/concepts + persisted match_reason
# --------------------------------------------------------------------------- #
def test_system_concepts_reason_visible_after_auto_assign(client, seed_concepts):
    sid_b = seed_concepts["sys_b"]
    r = client.post("/concepts/auto-assign")
    assert r.status_code == 200
    # auto-assign response carries the reason.
    assert any(
        a["reason"] == "name:'Funding' in entry_rule"
        for a in r.json()["assignments"]
    )

    items = client.get(f"/systems/{sid_b}/concepts").json()["items"]
    funding = next(i for i in items if i["name"] == "Funding")
    assert funding["source"] == "heuristic"
    assert funding["match_reason"] == "name:'Funding' in entry_rule"
    assert funding["concept_id"] == seed_concepts["concepts"]["Funding"]
    assert funding["created_at"] is not None


def test_system_concepts_manual_has_null_reason(client, seed_concepts):
    sid_vp = seed_concepts["sys_vp"]
    cid_vp = seed_concepts["concepts"]["Volume Profile"]
    client.post(f"/systems/{sid_vp}/concepts", json={"concept_id": cid_vp})

    items = client.get(f"/systems/{sid_vp}/concepts").json()["items"]
    vp = next(i for i in items if i["name"] == "Volume Profile")
    assert vp["source"] == "manual"
    assert vp["match_reason"] is None


def test_auto_assign_idempotent_keeps_reason(client, seed_concepts):
    sid_b = seed_concepts["sys_b"]
    client.post("/concepts/auto-assign")
    r2 = client.post("/concepts/auto-assign")
    assert r2.json()["created"] == 0

    items = client.get(f"/systems/{sid_b}/concepts").json()["items"]
    funding = next(i for i in items if i["name"] == "Funding")
    assert funding["match_reason"] == "name:'Funding' in entry_rule"


def test_system_concepts_404(client, seed_concepts):
    assert client.get("/systems/99999/concepts").status_code == 404


# --------------------------------------------------------------------------- #
# Phase 6, T13: auto-assign dry_run preview + confirm-with-provenance
# --------------------------------------------------------------------------- #
def test_auto_assign_dry_run_persists_nothing(client, seed_concepts, db_session):
    before = db_session.query(SystemConcept).count()

    r = client.post("/concepts/auto-assign", params={"dry_run": "true"})
    assert r.status_code == 200
    body = r.json()
    # Nothing written: created == 0 and the row count is unchanged.
    assert body["created"] == 0
    assert db_session.query(SystemConcept).count() == before

    # Preview lists genuine proposals with a reason and status='proposed'.
    assert len(body["assignments"]) > 0
    for a in body["assignments"]:
        assert a["status"] == "proposed"
        assert a["system_id"] is not None
        assert a["concept_id"] is not None
    pairs = {(a["system"], a["concept"]) for a in body["assignments"]}
    assert ("VP-M5-001", "Volume Profile") in pairs
    assert ("B-H1-801", "Funding") in pairs
    funding = next(a for a in body["assignments"] if a["concept"] == "Funding")
    assert funding["reason"] == "name:'Funding' in entry_rule"


def test_auto_assign_dry_run_skips_existing(client, seed_concepts, db_session):
    sid_vp = seed_concepts["sys_vp"]
    cid_vp = seed_concepts["concepts"]["Volume Profile"]
    client.post(f"/systems/{sid_vp}/concepts", json={"concept_id": cid_vp})

    body = client.post("/concepts/auto-assign", params={"dry_run": "true"}).json()
    # The already-assigned VP pair must not resurface as a proposal.
    pairs = {(a["system"], a["concept"]) for a in body["assignments"]}
    assert ("VP-M5-001", "Volume Profile") not in pairs
    assert body["skipped_existing"] >= 1


def test_auto_assign_real_run_unchanged_by_dry_run_param(client, seed_concepts):
    # dry_run defaults to false -> unchanged persisting behaviour.
    r = client.post("/concepts/auto-assign")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] > 0
    assert all(a["status"] == "created" for a in body["assignments"])


def test_confirm_proposal_keeps_heuristic_provenance(client, seed_concepts):
    sid_b = seed_concepts["sys_b"]
    cid_fund = seed_concepts["concepts"]["Funding"]

    r = client.post(
        f"/systems/{sid_b}/concepts",
        json={
            "concept_id": cid_fund,
            "source": "heuristic",
            "match_reason": "name:'Funding' in entry_rule",
        },
    )
    assert r.status_code == 201

    items = client.get(f"/systems/{sid_b}/concepts").json()["items"]
    funding = next(i for i in items if i["name"] == "Funding")
    assert funding["source"] == "heuristic"
    assert funding["match_reason"] == "name:'Funding' in entry_rule"
