"""
FastAPI application — the backend for Sales Lead Qualification & Outreach Agent.

Endpoints:
  POST  /leads        — submit a new lead, trigger the full agent loop, get back the result
  GET   /leads        — list all leads with scores and decisions
  GET   /leads/{id}   — full detail including reasoning trace and generated email
  PATCH /leads/{id}   — human edits the agent's drafted outreach email (review workflow)
"""

import json
import os
import sys

# Windows consoles often default to cp1252 which can't print emoji — force UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import google.generativeai as genai

from database import get_db, init_db
from models import Lead, LeadDecision
from agent import run_agent_loop


# ---------------------------------------------------------------------------
# Load environment and configure Gemini
# ---------------------------------------------------------------------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("⚠️  WARNING: GEMINI_API_KEY not set. Agent will use local fallback mode.")
    print("   Set it in .env or as an environment variable for the full LLM loop.")


# ---------------------------------------------------------------------------
# App lifespan — create tables on startup (+ optional auto-seed for demos)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✅ Database tables created / verified.")

    # Auto-seed demo data in production-like environments (e.g. Render free
    # tier starts with an empty DB). Local dev uses seed.py manually.
    if os.getenv("AUTO_SEED", "").lower() in ("1", "true", "yes"):
        from database import SessionLocal
        from seed import seed_leads

        db = SessionLocal()
        try:
            if db.query(Lead).count() == 0:
                print("🌱 AUTO_SEED enabled and DB empty — seeding demo leads...")
                seed_leads()
            else:
                print("✅ AUTO_SEED enabled but DB already has leads — skipping.")
        finally:
            db.close()

    yield


app = FastAPI(
    title="Sales Lead Qualification & Outreach Agent",
    description="Agentic AI tool for automated lead scoring and outreach",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js dev server, plus any production frontend origins
# passed via ALLOWED_ORIGINS (comma-separated), e.g. your Vercel URL.
# ---------------------------------------------------------------------------
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
extra_origins = os.getenv("ALLOWED_ORIGINS", "")
if extra_origins:
    allowed_origins += [o.strip() for o in extra_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class LeadCreate(BaseModel):
    """Input schema for a new lead."""
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    company: str = Field(..., min_length=1, max_length=255)
    title: str = Field(default="", max_length=255)
    message: str = Field(..., min_length=1)


class LeadResponse(BaseModel):
    """Output schema for a lead (list view)."""
    id: str
    name: str
    email: str
    company: str
    title: str | None
    message: str
    created_at: str
    score: int | None = None
    score_reason: str | None = None
    decision: str | None = None
    decision_status: str | None = None


class LeadDetailResponse(LeadResponse):
    """Full detail including trace and email."""
    enrichment_data: dict | None = None
    past_interaction_found: bool = False
    generated_email: str | None = None
    reasoning_trace: list = []


class EmailUpdate(BaseModel):
    """Body for PATCH /leads/{id} — a human edits the agent's draft."""
    generated_email: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/leads", response_model=LeadDetailResponse, status_code=201)
def create_lead(lead: LeadCreate, db: Session = Depends(get_db)):
    """
    Submit a new inbound lead.

    This kicks off the FULL agent loop:
      enrich → check history → score → decide → (optionally) draft email

    Returns the complete result with reasoning trace.
    """
    # 1. Save the raw lead
    db_lead = Lead(
        name=lead.name,
        email=lead.email,
        company=lead.company,
        title=lead.title,
        message=lead.message,
    )
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)

    # 2. Run the full agent loop
    lead_data = {
        "id": db_lead.id,
        "name": db_lead.name,
        "email": db_lead.email,
        "company": db_lead.company,
        "title": db_lead.title or "",
        "message": db_lead.message,
    }

    result = run_agent_loop(lead_data, db)

    # 3. Save the agent's decision
    db_decision = LeadDecision(
        lead_id=db_lead.id,
        enrichment_data=json.dumps(result.get("enrichment_data", {})),
        past_interaction_found=result.get("past_interactions", {}).get("status") == "returning",
        score=result.get("score", 0),
        score_reason=result.get("score_reason", ""),
        decision=result.get("decision", "needs-human-review"),
        generated_email=result.get("generated_email"),
        reasoning_trace=json.dumps(result.get("reasoning_trace", [])),
    )
    db.add(db_decision)
    db.commit()
    db.refresh(db_decision)

    # 4. Return the full result
    return _format_detail(db_lead, db_decision)


@app.get("/leads", response_model=list[LeadResponse])
def list_leads(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List all leads with their scores and decisions. Optionally filter by status."""
    query = db.query(Lead).order_by(Lead.created_at.desc())
    leads = query.all()

    results = []
    for lead in leads:
        decision = lead.decision
        item = LeadResponse(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            company=lead.company,
            title=lead.title,
            message=lead.message,
            created_at=lead.created_at.isoformat() if lead.created_at else "",
            score=decision.score if decision else None,
            score_reason=decision.score_reason if decision else None,
            decision=decision.decision if decision else None,
            decision_status=decision.decision if decision else None,
        )

        # Optional status filter
        if status and item.decision != status:
            continue

        results.append(item)

    return results


@app.get("/leads/{lead_id}", response_model=LeadDetailResponse)
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    """Get full detail for a single lead, including reasoning trace and generated email."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return _format_detail(lead, lead.decision)


@app.patch("/leads/{lead_id}", response_model=LeadDetailResponse)
def update_lead_email(lead_id: str, update: EmailUpdate, db: Session = Depends(get_db)):
    """
    Human-in-the-loop step: edit the agent's drafted outreach email.

    Used when a lead is in "needs-human-review" — the reviewer can refine the
    suggested draft before approving it. The original agent draft stays
    available in the reasoning trace; this updates the working copy.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    decision = lead.decision
    if not decision:
        raise HTTPException(status_code=400, detail="Lead has no decision yet")

    if not decision.generated_email:
        raise HTTPException(
            status_code=400,
            detail="This lead has no generated email to edit (discarded leads have no draft)",
        )

    decision.generated_email = update.generated_email.strip()
    db.commit()
    db.refresh(decision)

    return _format_detail(lead, decision)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_detail(lead: Lead, decision: LeadDecision | None) -> LeadDetailResponse:
    """Format a lead + decision into the detail response schema."""
    enrichment = {}
    trace = []
    if decision:
        try:
            enrichment = json.loads(decision.enrichment_data) if decision.enrichment_data else {}
        except (json.JSONDecodeError, TypeError):
            enrichment = {}
        try:
            trace = json.loads(decision.reasoning_trace) if decision.reasoning_trace else []
        except (json.JSONDecodeError, TypeError):
            trace = []

    return LeadDetailResponse(
        id=lead.id,
        name=lead.name,
        email=lead.email,
        company=lead.company,
        title=lead.title,
        message=lead.message,
        created_at=lead.created_at.isoformat() if lead.created_at else "",
        score=decision.score if decision else None,
        score_reason=decision.score_reason if decision else None,
        decision=decision.decision if decision else None,
        decision_status=decision.decision if decision else None,
        enrichment_data=enrichment,
        past_interaction_found=decision.past_interaction_found if decision else False,
        generated_email=decision.generated_email if decision else None,
        reasoning_trace=trace,
    )


# ---------------------------------------------------------------------------
# Run directly: python main.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # PORT is injected by hosts like Render. Ignore empty/0 values (some dev
    # machines have PORT=0 in the environment, which would bind a random port).
    raw_port = os.getenv("PORT", "").strip()
    port = int(raw_port) if raw_port.isdigit() and int(raw_port) > 0 else 8000
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
