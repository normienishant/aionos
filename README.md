# Sales Lead Qualification & Outreach Agent

An agentic AI tool for the Sales & Alliances track of the Agentic AI Factory program.

## Business Problem

Sales representatives at a company receive inbound leads (name, email, company, message) and waste hours each week:
1. **Manually researching** each lead's company (size, industry, relevance)
2. **Checking CRM** for prior interactions with the same person or company
3. **Scoring and deciding** whether the lead is worth pursuing
4. **Drafting the first outreach email** for promising leads

This agent automates all four steps in a single, end-to-end agentic loop — and makes its reasoning fully transparent.

---

## Why This Is "Agentic" (Not Just a Chatbot)

The key distinction: this is **not** a single LLM call that takes a prompt and returns an answer. It's a **multi-step autonomous loop** where the model:

1. **Plans** — receives the lead data and decides what to do first
2. **Calls a tool** — `enrich_company` to look up company data
3. **Observes the result** — sees the enrichment data
4. **Calls another tool** — `check_past_interactions` to check history
5. **Observes again** — now knows if this is new or returning
6. **Calls scoring tool** — `score_lead` with all gathered context
7. **Decides** — based on the score, autonomously picks one of three outcomes:
   - `auto-outreach-sent` (score ≥ 70): drafts an email and marks it as sent
   - `needs-human-review` (score 40-69): drafts an email as a suggestion, but requires human approval
   - `discarded` (score < 40): logs the reason, does nothing
8. **Reports back** — returns the full step-by-step reasoning trace

The **human-in-the-loop boundary** is explicit: borderline leads (40-69) are flagged for human review. The agent drafts a suggested email but does NOT mark it as sent — a human must approve first.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Lead Form │  │  Dashboard   │  │  Detail + Trace View │  │
│  └─────┬─────┘  └──────────────┘  └──────────────────────┘  │
│        │ POST /leads  →  GET /leads  →  GET /leads/:id      │
└────────┼────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│                                                             │
│  POST /leads ──→ Agent Loop (multi-step) ──→ Save & Return │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              THE AGENT LOOP                          │   │
│  │                                                      │   │
│  │  1. LLM receives lead data + tool definitions        │   │
│  │  2. LLM calls: enrich_company(company) ──→ mock DB   │   │
│  │  3. LLM calls: check_past_interactions(email)        │   │
│  │  4. LLM calls: score_lead(all_context) ──→ ICP rules │   │
│  │  5. Score ≥ 70? → LLM calls: draft_outreach_email() │   │
│  │  6. LLM returns final decision + reasoning           │   │
│  │                                                      │   │
│  │  Loop structure:                                     │   │
│  │    while model wants to call tools:                  │   │
│  │      execute tool → feed result back to LLM          │   │
│  │    when no more tools → parse final decision         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  SQLAlchemy ──→ PostgreSQL / SQLite                         │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Database (2 tables)                       │
│                                                             │
│  leads              │  lead_decisions                       │
│  ─────              │  ──────────────                       │
│  id (PK)            │  id (PK)                              │
│  name               │  lead_id (FK → leads)                 │
│  email              │  enrichment_data (JSON)               │
│  company            │  past_interaction_found (BOOL)        │
│  title              │  score (INT)                          │
│  message            │  score_reason (TEXT)                   │
│  created_at         │  decision (TEXT)                       │
│                     │  generated_email (TEXT)               │
│                     │  reasoning_trace (JSON)               │
│                     │  created_at                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Setup & Run

### Prerequisites
- Python 3.11+
- Node.js 18+
- A Google Gemini API key ([get one free](https://aistudio.google.com/apikey))

### 1. Backend

```bash
cd backend

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# Seed the database with 7 mock leads
python seed.py

# Start the backend server
python main.py
# Runs on http://localhost:8000
```

### 2. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
# Runs on http://localhost:3000
```

### 3. Open the app

Visit **http://localhost:3000** in your browser.

- **Dashboard** (`/`) — see all leads with scores and color-coded status badges
- **Submit Lead** (`/submit`) — enter a new lead and watch the agent process it
- **Lead Detail** (`/leads/:id`) — full view of enrichment data, score reasoning, the complete tool-call trace, and any generated email

### Without Gemini API Key

The app works without an API key — the seed script falls back to local scoring (no LLM), and the agent loop will show a warning. Set `GEMINI_API_KEY` in `.env` for the full agentic experience.

---

## What the Agent Decides vs. What Humans Decide

| Decision | Agent or Human? | Details |
|---|---|---|
| Enrich company data | 🤖 Agent | Uses mock enrichment (would be Clearbit/Apollo in production) |
| Check past interactions | 🤖 Agent | Queries the DB automatically |
| Score the lead (0-100) | 🤖 Agent | Applies ICP rules with clear reasoning |
| Auto-outreach (score ≥ 70) | 🤖 Agent | Agent drafts email, marks as "sent" |
| Suggest outreach (40-69) | 🤖 Agent drafts, 👤 Human approves | Email is a suggestion only — must be reviewed before sending |
| Discard (score < 40) | 🤖 Agent | Logged with reason for audit trail |

---

## ICP Scoring Rules (0-100)

| Factor | Max Points | Logic |
|---|---|---|
| Company Size | 25 | Enterprise/large → 25, mid-size → 15, small → 10, startup → 2 |
| Industry Match | 25 | SaaS/Fintech/Enterprise/Cloud → 25, others → 10 |
| Inquiry Intent | 25 | Keywords like "pricing", "demo", "budget", "enterprise" → 8pts each, max 25 |
| Returning Lead | 15 | Has prior interactions → 15, new → 0 |
| Professional Email | 6 | Corporate domain → 6, free email (Gmail, Yahoo) → 0 |
| Senior Title | 4 | VP/Director/Head/CTO → 4, other title → 0 |

---

## Tech Stack

- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL (via SQLAlchemy) — falls back to SQLite for local dev
- **LLM**: Google Gemini 1.5 Flash (with function calling / tool use)
- **No frameworks**: Agent loop is implemented directly with the LLM's native function-calling API — transparent, explainable, no "black box"

---

## File Structure

```
sales-lead-agent/
├── README.md                    ← You are here
├── backend/
│   ├── requirements.txt         ← Python dependencies
│   ├── .env.example             ← Environment variable template
│   ├── database.py              ← SQLAlchemy connection + session
│   ├── models.py                ← Lead + LeadDecision models
│   ├── tools.py                 ← 4 tool functions (enrich, check, score, draft)
│   ├── agent.py                 ← THE AGENT LOOP — core of the system
│   ├── main.py                  ← FastAPI app + endpoints
│   └── seed.py                  ← Seed 7 mock leads for demo
└── frontend/
    ├── package.json
    ├── next.config.js           ← API proxy to backend
    ├── tailwind.config.js
    ├── tsconfig.json
    └── src/
        └── app/
            ├── globals.css
            ├── layout.tsx       ← Root layout with nav
            ├── page.tsx         ← Dashboard (lead table)
            ├── submit/
            │   └── page.tsx     ← Lead submission form
            └── leads/
                └── [id]/
                    └── page.tsx ← Lead detail + reasoning trace
```
