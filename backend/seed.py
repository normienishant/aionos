"""
Seed script — populates the database with 7 realistic leads to demo all three paths.

Run: cd backend && python seed.py

The leads are designed to test every decision path:
  - Leads 1-3: High score (≥70) → auto-outreach-sent
  - Leads 4-5: Mid score (40-69) → needs-human-review
  - Leads 6-7: Low score (<40) → discarded

Each lead has different enrichment characteristics to show the scoring logic working.
"""

import json
import os
import sys
import time

# Windows consoles often default to cp1252 which can't print emoji — force UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
import google.generativeai as genai

from database import init_db, SessionLocal
from models import Lead, LeadDecision
from tools import enrich_company, check_past_interactions, score_lead, draft_outreach_email
from agent import run_agent_loop


# Load .env
load_dotenv()

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("⚠️  GEMINI_API_KEY not set. Will seed with mock decisions only (no agent loop).")


MOCK_LEADS = [
    # === HIGH SCORE (≥70) — should auto-outreach ===
    {
        "name": "Priya Sharma",
        "email": "priya.sharma@techcorp.com",
        "company": "TechCorp Solutions",
        "title": "VP of Engineering",
        "message": "We're looking at enterprise integration platforms for our team of 200+. We have a budget of ₹50L annual and need a demo next week. Could you send a proposal?",
    },
    {
        "name": "Marcus Johnson",
        "email": "marcus.j@cloudnine.io",
        "company": "CloudNine",
        "title": "Head of Sales",
        "message": "Interested in your pricing for an annual enterprise contract. We're migrating from a competitor and need pilot access for evaluation. Team of 50 people.",
    },
    {
        "name": "Sarah Chen",
        "email": "sarah.chen@globalfinance.com",
        "company": "Global Finance Partners",
        "title": "Director of Operations",
        "message": "We need a custom integration with our existing ERP system. Budget approved for Q1. Looking at enterprise solutions — can we schedule a demo?",
    },

    # === MID SCORE (40-69) — should need human review ===
    {
        "name": "Alex Rivera",
        "email": "alex.r@creativestudio.co",
        "company": "Creative Studio",
        "title": "Project Manager",
        "message": "Just curious about your product. We're a small design agency (15 people) and wondering if this could help with our workflow. No immediate budget, maybe next quarter.",
    },
    {
        "name": "Fatima Al-Rashid",
        "email": "fatima@growthmetrics.com",
        "company": "GrowthMetrics",
        "title": "Business Analyst",
        "message": "Hi, we're evaluating several options for our team. Could you share pricing and maybe a quick demo? We have about 80 people and might be interested if the ROI makes sense.",
    },

    # === LOW SCORE (<40) — should discard ===
    {
        "name": "Tommy Lee",
        "email": "tommy.lee@gmail.com",
        "company": "Tommy's Pizza Shop",
        "title": "",
        "message": "Hey, just stumbled on your website. Cool stuff! I run a pizza place and wondering if you guys do anything for restaurants? Probably not but thought I'd ask lol",
    },
    {
        "name": "Jane Doe",
        "email": "jane.doe@yahoo.com",
        "company": "Freelance Photography",
        "title": "Freelancer",
        "message": "Hi, I'm a freelance photographer. Do you have a free tier? I don't have much budget. Thanks!",
    },
]


def seed_leads():
    """Seed the database with mock leads and run the agent loop on each."""
    init_db()
    db = SessionLocal()

    # Check if already seeded
    existing = db.query(Lead).count()
    if existing > 0:
        print(f"⚠️  Database already has {existing} leads. Clearing before re-seeding...")
        db.query(LeadDecision).delete()
        db.query(Lead).delete()
        db.commit()

    print(f"\n🌱 Seeding {len(MOCK_LEADS)} mock leads...\n")

    for i, lead_data in enumerate(MOCK_LEADS, 1):
        # Gentle pacing so the free-tier LLM per-minute rate limit isn't hammered
        if i > 1:
            time.sleep(8)
        print(f"--- Lead {i}/{len(MOCK_LEADS)}: {lead_data['name']} ({lead_data['company']}) ---")

        # Create the lead
        db_lead = Lead(
            name=lead_data["name"],
            email=lead_data["email"],
            company=lead_data["company"],
            title=lead_data["title"],
            message=lead_data["message"],
        )
        db.add(db_lead)
        db.commit()
        db.refresh(db_lead)

        # Run agent loop if API key is available
        if GEMINI_API_KEY:
            try:
                result = run_agent_loop(
                    {
                        "id": db_lead.id,
                        "name": db_lead.name,
                        "email": db_lead.email,
                        "company": db_lead.company,
                        "title": db_lead.title or "",
                        "message": db_lead.message,
                    },
                    db,
                )

                decision = LeadDecision(
                    lead_id=db_lead.id,
                    enrichment_data=json.dumps(result.get("enrichment_data", {})),
                    past_interaction_found=result.get("past_interactions", {}).get("status") == "returning",
                    score=result.get("score", 0),
                    score_reason=result.get("score_reason", ""),
                    decision=result.get("decision", "needs-human-review"),
                    generated_email=result.get("generated_email"),
                    reasoning_trace=json.dumps(result.get("reasoning_trace", [])),
                )
                db.add(decision)
                db.commit()

                status = result["decision"]
                score = result["score"]
                emoji = "🟢" if status == "auto-outreach-sent" else "🟡" if status == "needs-human-review" else "🔴"
                print(f"  {emoji} Score: {score} → Decision: {status}")
            except Exception as e:
                print(f"  ❌ Agent loop failed: {e}")
                print(f"     (This is expected if GEMINI_API_KEY is not set)")
        else:
            # Fallback: use local scoring only (no LLM)
            enrichment = enrich_company(lead_data["company"])
            past = check_past_interactions(lead_data["email"], lead_data["company"], db, exclude_lead_id=db_lead.id)
            result = score_lead(
                lead_data["name"], lead_data["email"], lead_data["company"],
                lead_data["title"], lead_data["message"], enrichment, past,
            )
            score = result["score"]

            if score >= 70:
                decision_status = "auto-outreach-sent"
                email = draft_outreach_email(
                    lead_data["name"], lead_data["company"], lead_data["title"],
                    lead_data["message"], enrichment, score, result["reasoning"],
                )
            elif score >= 40:
                decision_status = "needs-human-review"
                email = draft_outreach_email(
                    lead_data["name"], lead_data["company"], lead_data["title"],
                    lead_data["message"], enrichment, score, result["reasoning"],
                )
            else:
                decision_status = "discarded"
                email = None

            db_decision = LeadDecision(
                lead_id=db_lead.id,
                enrichment_data=json.dumps(enrichment),
                past_interaction_found=past["status"] == "returning",
                score=score,
                score_reason=result["reasoning"],
                decision=decision_status,
                generated_email=email,
                reasoning_trace=json.dumps([
                    {"step": 1, "tool_called": "enrich_company", "result": enrichment},
                    {"step": 2, "tool_called": "check_past_interactions", "result": past},
                    {"step": 3, "tool_called": "score_lead", "result": result},
                ]),
            )
            db.add(db_decision)
            db.commit()

            emoji = "🟢" if decision_status == "auto-outreach-sent" else "🟡" if decision_status == "needs-human-review" else "🔴"
            print(f"  {emoji} Score: {score} → Decision: {decision_status} (local scoring)")

    db.close()
    print(f"\n✅ Seeded {len(MOCK_LEADS)} leads successfully!")
    print(f"   Start the backend:  cd backend && python main.py")
    print(f"   Start the frontend: cd frontend && npm run dev")


if __name__ == "__main__":
    seed_leads()
