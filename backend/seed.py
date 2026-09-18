"""
Seed script — populates the database with 8 realistic leads to demo all three paths.

Run: cd backend && python seed.py

The leads are designed to test every decision path:
  - Leads 1, 3:   high score (≥70)  → auto-outreach-sent
  - Leads 2, 4, 5: borderline        → needs-human-review
  - Leads 6-8:    low score (<40)   → discarded
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
        "email": "priya.sharma@zenithsoftech.in",
        "company": "Zenith Softech",
        "title": "VP Engineering",
        "message": "Hi, we saw your booth at NASSCOM Product Conclave. We're evaluating integration platforms for our 400-seat engineering org. Budget of ₹65 lakh approved for this FY. Can you share pricing and set up a demo next week? Also need the GST quotation format for procurement.",
    },
    {
        "name": "Rohit Deshpande",
        "email": "rohit.deshpande@vardhmanlogistics.co.in",
        "company": "Vardhman Logistics",
        "title": "Head of Operations",
        "message": "We run 220 trucks across 11 states and are migrating from Tally to a proper ops platform. Need custom ERP integration and a pilot in our Nagpur hub first. Procurement wants an RFP — can your team participate?",
    },
    {
        "name": "Kavitha Raman",
        "email": "kavitha.r@meridianfintech.com",
        "company": "Meridian FinTech",
        "title": "Director - Product",
        "message": "We're a Series-B fintech (220 people, Bengaluru) scaling our lending ops. Your platform was recommended by our investors. Need enterprise pricing for annual contract, and a demo for our product council. Timeline: this quarter.",
    },

    # === MID SCORE (40-69) — should need human review ===
    {
        "name": "Arjun Nair",
        "email": "arjun.nair@blueoakconsulting.in",
        "company": "BlueOak Consulting",
        "title": "Project Manager",
        "message": "Hello, we're a 40-person consulting firm in Kochi. Curious if this could work for client onboarding. No fixed budget yet — partner saab will approve if the ROI is clear. Maybe share some case studies?",
    },
    {
        "name": "Meenakshi Sundaram",
        "email": "meena.s@srilakshmitextiles.com",
        "company": "Sri Lakshmi Textiles",
        "title": "GM - Exports",
        "message": "We export garments to EU buyers and they want digital tracking. We are about 90 people in Tirupur. What would pricing look like for something like this? Do you give a demo before we decide?",
    },

    # === LOW SCORE (<40) — should discard ===
    {
        "name": "Rajesh Kirana Store",
        "email": "rajesh.kirana@gmail.com",
        "company": "Rajesh Kirana & General Store",
        "title": "",
        "message": "Namaste sir, maine aapki website dekhi. Mera kirana shop hai Jaipur me. Aapka software humko sasta milega kya? GST bill bhi hota hai isme? Rate batao please.",
    },
    {
        "name": "Pooja Makeover Studio",
        "email": "pooja.beauty@yahoo.com",
        "company": "Pooja Makeover Studio",
        "title": "Owner",
        "message": "Hi! I run a beauty studio in Lucknow. Koi free trial hai? Budget nahi hai abhi, baad me dekhenge. Instagram pe bhi kaam karta hai kya ye?",
    },
    {
        "name": "Deepak Tuition Classes",
        "email": "deepak.classes@rediffmail.com",
        "company": "Deepak Tuition Classes",
        "title": "Teacher",
        "message": "Sir I am running tuition classes for 10th-12th science in Indore since 12 years. Aapka product school ke liye hai ya coaching ke liye bhi? Fees kitni hai per month? Beta ke school me bhi bhej sakta hu.",
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
