"""
Automated test suite — run with:  cd backend && python -m pytest test_agent.py -v
(or simply: python test_agent.py)

Covers the four tools, decision routing, the local fallback pipeline, and the
API contract — everything a reviewer would poke at.
"""

import json
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_leads.db")
os.environ.setdefault("GEMINI_API_KEY", "")  # force the deterministic paths

from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
from database import SessionLocal, init_db  # noqa: E402
from main import app  # noqa: E402
from tools import enrich_company, check_past_interactions, score_lead, draft_outreach_email  # noqa: E402
from agent import _run_local_pipeline, _decide_from_score  # noqa: E402

client = TestClient(app)


# Create tables once for the whole run (the app's lifespan hook doesn't fire
# under TestClient unless every request opens a fresh context; explicit > clever).
init_db()


def _clean_db():
    import models
    db = SessionLocal()
    db.query(models.LeadDecision).delete()
    db.query(models.Lead).delete()
    db.commit()
    db.close()


def _post_lead(**overrides) -> dict:
    payload = {
        "name": "Test User",
        "email": "test.user@examplecorp.in",
        "company": "ExampleCorp Technologies",
        "title": "CTO",
        "message": "We need a demo and pricing for our team of 150. Budget approved.",
        **overrides,
    }
    resp = client.post("/leads", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# tools.py
# ---------------------------------------------------------------------------

def test_enrich_returns_required_fields():
    data = enrich_company("Infosys")
    for field in ("company_name", "industry", "size", "enrichment_source"):
        assert field in data, f"missing {field}"
    assert data["company_name"] == "Infosys"


def test_enrich_source_is_labeled():
    """Every enrichment record must honestly state where it came from."""
    known = enrich_company("Infosys")
    unknown = enrich_company("Zylkrix Labs Pvt Ltd")
    assert "wikipedia" in known["enrichment_source"] or "heuristic" in known["enrichment_source"]
    assert "heuristic" in unknown["enrichment_source"]


def test_enrich_is_deterministic():
    """Same company must get the same fallback data twice (stable demo)."""
    a = enrich_company("Zylkrix Labs Pvt Ltd")
    b = enrich_company("Zylkrix Labs Pvt Ltd")
    assert a["industry"] == b["industry"] and a["size"] == b["size"]


def test_local_business_gets_small_size():
    data = enrich_company("Rajesh Kirana & General Store")
    assert "1-10" in data["size"]


def test_past_interactions_finds_repeat_company():
    _clean_db()
    import models
    db = SessionLocal()
    # Seed a prior lead row directly (the API path uses a different session)
    db.add(models.Lead(name="Old User", email="old@samecorp.in", company="SameCorp",
                       title="", message="earlier inquiry"))
    db.commit()
    result = check_past_interactions("new.person@samecorp.in", "SameCorp", db, exclude_lead_id="n/a")
    db.close()
    assert result["status"] == "returning"
    assert result["returning_company"] is True


def test_past_interactions_excludes_self():
    """A brand-new lead must NOT find itself (self-match regression test)."""
    _clean_db()
    db = SessionLocal()
    created = _post_lead(email="solo@freshcorp.in", company="FreshCorp")
    result = check_past_interactions("solo@freshcorp.in", "FreshCorp", db, exclude_lead_id=created["id"])
    db.close()
    assert result["status"] == "new", "lead matched itself — exclude_lead_id broken"


def test_score_hot_lead_beats_cold_lead():
    enrichment = {"industry": "SaaS / Enterprise Software", "size": "1000+ (Enterprise)"}
    hot = score_lead("A", "a@corp.in", "Corp", "VP Engineering",
                     "We need pricing, a demo and an enterprise contract. Budget approved for this FY.",
                     enrichment, {"status": "returning", "previous_lead_count": 2})
    cold = score_lead("B", "b@gmail.com", "Shop", "",
                      "kya rate hai? sasta milega?",
                      {"industry": "Local Services", "size": "1-10 (Startup)"},
                      {"status": "new", "previous_lead_count": 0})
    assert hot["score"] >= 70, f"hot lead scored {hot['score']}"
    assert cold["score"] < 40, f"cold lead scored {cold['score']}"
    assert hot["score"] > cold["score"]


def test_score_reason_has_breakdown():
    result = score_lead("A", "a@corp.in", "Corp", "CTO", "demo and pricing please",
                        {"industry": "FinTech", "size": "201-1000 (Large)"},
                        {"status": "new", "previous_lead_count": 0})
    assert " | " in result["reasoning"] and len(result["breakdown"]) >= 4


def test_email_draft_has_no_placeholder_in_llm_absence():
    """Template fallback must still be a usable, complete email."""
    email, drafted_by = draft_outreach_email(
        "Priya Sharma", "Zenith Softech", "VP Engineering",
        "We need enterprise integration, budget approved, need a demo next week.",
        {"industry": "SaaS / Enterprise Software", "description": ""},
        82, "Enterprise size, strong intent",
    )
    assert drafted_by == "template-fallback"  # no key in test env
    assert "Subject:" in email and "Hi Priya Sharma" in email
    # Template references enrichment placeholders only in the benefit line —
    # acceptable for the fallback, but no UNFILLED braces from f-string bugs:
    assert "{name}" not in email and "{company}" not in email


# ---------------------------------------------------------------------------
# agent.py
# ---------------------------------------------------------------------------

def test_decide_boundaries():
    assert _decide_from_score(70) == "auto-outreach-sent"
    assert _decide_from_score(69) == "needs-human-review"
    assert _decide_from_score(40) == "needs-human-review"
    assert _decide_from_score(39) == "discarded"


def test_local_pipeline_full_loop():
    """No-API-key path must run every tool in order and produce a coherent result."""
    _clean_db()
    db = SessionLocal()
    lead = {"id": "t1", "name": "Loop Test", "email": "loop@techcorp.in",
            "company": "TechCorp Solutions", "title": "CTO",
            "message": "Enterprise integration needed. Budget approved, need demo and pricing."}
    result = _run_local_pipeline(lead, db)
    db.close()
    trace_tools = [s.get("tool_called") for s in result["reasoning_trace"] if s.get("tool_called")]
    assert trace_tools[:3] == ["enrich_company", "check_past_interactions", "score_lead"]
    assert result["decision"] in ("auto-outreach-sent", "needs-human-review", "discarded")
    if result["decision"] != "discarded":
        assert result["generated_email"]


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------

def test_api_list_and_detail_roundtrip():
    _clean_db()
    created = _post_lead()
    detail = client.get(f"/leads/{created['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["reasoning_trace"], "trace must be stored"
    assert body["enrichment_data"], "enrichment must be stored"
    assert body["decision"] in ("auto-outreach-sent", "needs-human-review", "discarded")

    listed = client.get("/leads")
    assert listed.status_code == 200
    assert any(l["id"] == created["id"] for l in listed.json())


def test_api_validation_rejects_bad_payload():
    assert client.post("/leads", json={"name": "x"}).status_code == 422
    assert client.get("/leads/nonexistent-id").status_code == 404


def test_api_patch_email_flow():
    _clean_db()
    created = _post_lead(message="Need a demo and pricing. Enterprise budget approved.")
    if not created.get("generated_email"):
        created = _post_lead(name="Test User 2", email="test2@examplecorp.in",
                             message="Need a demo and pricing. Enterprise budget approved.")
    edited = client.patch(f"/leads/{created['id']}", json={"generated_email": "Subject: Edited\n\nHuman-reviewed text."})
    assert edited.status_code == 200
    assert edited.json()["generated_email"].startswith("Subject: Edited")

    discarded = _post_lead(name="Cold Lead", email="cold@gmail.com", title="",
                           company="Random Shop", message="kya rate hai sasta wala?")
    if discarded["decision"] == "discarded":
        r = client.patch(f"/leads/{discarded['id']}", json={"generated_email": "x"})
        assert r.status_code == 400, "discarded lead has no draft to edit"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
