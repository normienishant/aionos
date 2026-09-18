"""
Agent tool functions.

These are the four distinct tools the LLM agent can invoke via function calling.
Each is a standalone Python function so it can be swapped or upgraded without
touching the agent loop.

Real integrations used:
  - enrich_company: live Wikipedia REST API lookup (summary + extract), with a
    clearly-labeled deterministic fallback when a company has no article or
    the network is unavailable.
  - draft_outreach_email: a real Gemini LLM call that writes a personalized
    email from the lead's context, with a template fallback.
"""

import json
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session
from models import Lead, LeadDecision

# Model for email generation — default is flash-LITE: the free tier gives it a
# much larger daily quota than regular flash. Resolves via the "latest" alias.
_EMAIL_MODEL = os.getenv("LLM_MODEL", "gemini-flash-lite-latest")

# Wikimedia's robot policy requires a descriptive User-Agent with contact info.
_WIKI_UA = "SalesLeadQualificationAgent/1.0 (educational demo; contact via github.com/normienishant) httpx"


def enrich_company(company_name: str) -> dict:
    """
    TOOL: enrich_company

    Given a company name, return enrichment data. Primary source: the live
    Wikipedia REST API (real third-party HTTP call — free, no API key needed).
    If the company has no Wikipedia article (most small/private companies),
    falls back to deterministic heuristic data that is honestly labeled.
    """
    name_lower = company_name.lower().strip()
    name_hash = sum(ord(c) for c in name_lower)

    # --- Attempt 1: real Wikipedia REST API lookup (summary + extract) ---
    article_title = None
    extract = None
    try:
        search_resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": company_name,
                "format": "json", "srlimit": 1,
            },
            headers={"User-Agent": _WIKI_UA},
            timeout=8.0,
        )
        hits = search_resp.json().get("query", {}).get("search", [])
        if hits:
            article_title = hits[0]["title"]
            # Cheap relevance filter: at least one significant word of the
            # company name should appear in the article title.
            significant = [w for w in name_lower.split() if len(w) > 2 and w not in ("the", "and", "for", "ltd", "llc", "inc", "group")]
            if significant and not any(w in article_title.lower() for w in significant):
                article_title = None
        if article_title:
            sum_resp = httpx.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{article_title.replace(' ', '_')}",
                headers={"User-Agent": _WIKI_UA},
                timeout=8.0,
            )
            extract = (sum_resp.json().get("extract") or "")[:600] or None
    except (httpx.HTTPError, ValueError, KeyError):
        article_title = None  # network error / bad JSON → fall through to fallback
        extract = None

    if article_title and extract:
        return {
            "company_name": company_name,
            "matched_wikipedia_article": article_title,
            "industry": _classify_industry(extract),
            "size": "See description (Wikipedia-verified organization)",
            "region": "See description",
            "description": extract,
            "enrichment_source": f"wikipedia_api ({datetime.now(timezone.utc).date().isoformat()})",
        }

    # --- Fallback: deterministic heuristic data, honestly labeled ---
    industries = [
        "SaaS / Enterprise Software", "FinTech", "HealthTech", "E-Commerce / Retail",
        "Manufacturing", "Consulting / Professional Services", "EdTech", "Logistics / Supply Chain",
    ]
    regions = ["North America", "Europe", "APAC", "LATAM", "Middle East", "India / South Asia"]
    sizes = ["1-10 (Startup)", "11-50 (Small)", "51-200 (Mid-size)", "201-1000 (Large)", "1000+ (Enterprise)"]

    known = {
        "google":    {"industry": "Technology / Cloud", "size": "10000+ (Enterprise)", "region": "North America", "website": "google.com", "founded": 1998},
        "microsoft": {"industry": "Technology / Enterprise Software", "size": "10000+ (Enterprise)", "region": "North America", "website": "microsoft.com", "founded": 1975},
        "amazon":    {"industry": "E-Commerce / Cloud / Logistics", "size": "10000+ (Enterprise)", "region": "North America", "website": "amazon.com", "founded": 1994},
        "apple":     {"industry": "Consumer Electronics / Technology", "size": "10000+ (Enterprise)", "region": "North America", "website": "apple.com", "founded": 1976},
        "meta":      {"industry": "Social Media / Advertising", "size": "10000+ (Enterprise)", "region": "North America", "website": "meta.com", "founded": 2004},
        "startupco":{"industry": "SaaS / Enterprise Software", "size": "11-50 (Small)", "region": "India / South Asia", "website": "startupco.io", "founded": 2021},
    }

    if name_lower in known:
        data = known[name_lower]
    else:
        # Heuristics: name markers → industry; name length → size bucket.
        # Non-corporate names get small-business enrichment so scoring
        # penalizes them naturally.
        local_business_markers = ["shop", "pizza", "cafe", "salon", "freelance",
                                  "photography", "restaurant", "store", "boutique",
                                  "lawn", "cleaning", "repair", "tutor"]
        is_local_business = any(m in name_lower for m in local_business_markers)

        if is_local_business:
            size = sizes[0]  # 1-10 (Startup)
        elif len(name_lower) >= 15:
            size = sizes[3 if name_hash % 2 == 0 else 4]   # Large or Enterprise
        elif len(name_lower) >= 8:
            size = sizes[2]                                 # Mid-size
        else:
            size = sizes[0 if name_hash % 2 == 0 else 1]    # Startup or Small

        industry_markers = [
            (["software", "tech", "cloud", "saas", "systems", "solutions", "labs", "digital"], "SaaS / Enterprise Software"),
            (["finance", "financial", "bank", "capital", "credit", "invest"], "FinTech"),
            (["health", "med", "pharma", "clinic"], "HealthTech"),
            (["logistics", "shipping", "freight", "cargo"], "Logistics / Supply Chain"),
            (["consult", "advisory", "partners"], "Consulting / Professional Services"),
            (["learn", "edu", "academy", "training"], "EdTech"),
            (["commerce", "retail", "mart", "goods"], "E-Commerce / Retail"),
        ]
        industry = None
        for markers, ind in industry_markers:
            if any(m in name_lower for m in markers):
                industry = ind
                break
        if industry is None:
            industry = industries[name_hash % len(industries)]

        if is_local_business:
            local_industries = ["Food & Beverage / Local Retail", "Local Services / Sole Proprietor"]
            industry = local_industries[name_hash % len(local_industries)]

        data = {
            "industry": industry,
            "size": size,
            "region": regions[name_hash % len(regions)],
            "website": f"{name_lower.replace(' ', '')}.com",
            "founded": 2000 + (name_hash % 24),
        }

    return {
        "company_name": company_name,
        **data,
        "enrichment_source": "heuristic_fallback (no wikipedia match)",
    }


def _classify_industry(extract: str) -> str:
    """Classify an industry from a Wikipedia extract via keyword matching."""
    text = extract.lower()
    industry_markers = [
        (["software", "technology", "cloud", "saas", "computing", "ai "], "Technology / Cloud"),
        (["bank", "financial", "finance", "insurance", "payment"], "Financial Services"),
        (["retail", "e-commerce", "ecommerce", "shopping"], "E-Commerce / Retail"),
        (["pharmaceutical", "healthcare", "hospital", "medical"], "Healthcare"),
        (["manufactur", "automotive", "industrial"], "Manufacturing"),
        (["consulting", "professional services", "advisory"], "Consulting / Professional Services"),
        (["telecommunication", "telecom", "wireless"], "Telecommunications"),
        (["media", "entertainment", "film", "streaming"], "Media / Entertainment"),
    ]
    for markers, industry in industry_markers:
        if any(m in text for m in markers):
            return industry
    return "Diversified / Other"


def check_past_interactions(email: str, company_name: str, db: Session, exclude_lead_id: str | None = None) -> dict:
    """
    TOOL: check_past_interactions
    Query the DB for any prior leads from the same email or company.
    Returns whether this is a new or returning lead.

    exclude_lead_id: the current lead's own id, so we don't count the lead
    as an "interaction with itself" (it's already saved before scoring runs).
    """
    # Check by email (excluding the current lead itself)
    email_query = db.query(Lead).filter(Lead.email.ilike(email))
    if exclude_lead_id:
        email_query = email_query.filter(Lead.id != exclude_lead_id)
    existing_by_email = email_query.first()

    # Check by company (excluding the current lead itself)
    company_query = db.query(Lead).filter(Lead.company.ilike(company_name))
    if exclude_lead_id:
        company_query = company_query.filter(Lead.id != exclude_lead_id)
    existing_by_company = company_query.all()

    result = {
        "returning_email": existing_by_email is not None,
        "returning_company": len(existing_by_company) > 0,
        "previous_lead_count": len(existing_by_company),
        "previous_lead_ids": [l.id for l in existing_by_company],
        "status": "new" if not existing_by_email and len(existing_by_company) == 0 else "returning",
    }

    if existing_by_email:
        result["first_seen_email"] = existing_by_email.created_at.isoformat()

    return result


def score_lead(
    name: str,
    email: str,
    company: str,
    title: str,
    message: str,
    enrichment_data: dict,
    past_interactions: dict,
) -> dict:
    """
    TOOL: score_lead
    Compute a lead score 0-100 based on ICP (Ideal Customer Profile) rules.
    Returns score + written reasoning.

    ICP Rules (configurable):
      - Company size match (25 pts)
      - Industry relevance (25 pts)
      - Inquiry intent / keyword match (25 pts)
      - Returning lead bonus (15 pts)
      - Professional email / title bonus (10 pts)
    """
    score = 0
    reasons = []

    # --- Company Size (25 pts) ---
    size = enrichment_data.get("size", "")
    if "1000+" in size or "10000+" in size or "Enterprise" in size:
        score += 25
        reasons.append("Company size: Enterprise/large (+25)")
    elif "Wikipedia-verified" in size:
        # Notable enough to have an encyclopedia article — solid mid signal
        score += 15
        reasons.append("Notable organization (Wikipedia-verified) (+15)")
    elif "201" in size or "Large" in size:
        score += 20
        reasons.append("Company size: Large (+20)")
    elif "51" in size or "Mid" in size:
        score += 15
        reasons.append("Company size: Mid-size (+15)")
    elif "11" in size or "Small" in size:
        score += 10
        reasons.append("Company size: Small (+10)")
    else:
        score += 2
        reasons.append("Company size: Startup/very small (+2)")

    # --- Industry Match (25 pts) ---
    high_value_industries = ["saas", "enterprise", "fintech", "financial", "cloud", "consulting", "technology", "software"]
    industry = enrichment_data.get("industry", "").lower()
    if any(ind in industry for ind in high_value_industries):
        score += 25
        reasons.append(f"Industry match — high-value vertical: {enrichment_data.get('industry')} (+25)")
    else:
        score += 10
        reasons.append(f"Industry partial match: {enrichment_data.get('industry')} (+10)")

    # --- Inquiry Intent / Keywords (25 pts) ---
    intent_keywords = [
        "pricing", "demo", "trial", "integrat", "pilot", "enterprise",
        "scale", "migration", "custom", "contract", "purchase", "buy",
        "budget", "proposal", "rfp", "evaluation", "assessment", "annual",
    ]
    message_lower = message.lower()
    matched_keywords = [kw for kw in intent_keywords if kw in message_lower]
    keyword_score = min(25, len(matched_keywords) * 8)
    score += keyword_score
    if matched_keywords:
        reasons.append(f"Inquiry intent keywords found: {', '.join(matched_keywords)} (+{keyword_score})")
    else:
        reasons.append("No strong intent keywords in inquiry (+0)")

    # --- Returning Lead Bonus (15 pts) ---
    if past_interactions.get("status") == "returning":
        score += 15
        reasons.append(f"Returning lead — {past_interactions.get('previous_lead_count', 0)} prior interaction(s) (+15)")
    else:
        reasons.append("New lead, no prior interactions (+0)")

    # --- Professional Email / Title Bonus (10 pts) ---
    free_email_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "protonmail.com"]
    email_domain = email.split("@")[-1].lower() if "@" in email else ""
    if email_domain and email_domain not in free_email_domains:
        score += 6
        reasons.append(f"Corporate email domain: {email_domain} (+6)")
    else:
        reasons.append("Free/personal email domain (+0)")

    if title and title.strip():
        senior_keywords = ["director", "vp", "head", "chief", "cto", "ceo", "cfo", "coo", "president", "manager", "lead"]
        if any(kw in title.lower() for kw in senior_keywords):
            score += 4
            reasons.append(f"Senior title detected: {title} (+4)")
        else:
            reasons.append(f"Title present but not senior: {title} (+0)")

    # Clamp to 0-100
    score = max(0, min(100, score))

    return {
        "score": score,
        "reasoning": " | ".join(reasons),
        "breakdown": reasons,
    }


def draft_outreach_email(
    name: str,
    company: str,
    title: str,
    message: str,
    enrichment_data: dict,
    score: int,
    score_reason: str,
) -> tuple[str, str]:
    """
    TOOL: draft_outreach_email

    Generates a personalized first outreach email. Primary path: a real Gemini
    LLM call conditioned on the lead's data and enrichment context. If the LLM
    is unavailable (no key / quota / network), falls back to the template so
    the loop never breaks.

    Returns (email_text, drafted_by) where drafted_by is "gemini-llm" or
    "template-fallback" — recorded in the reasoning trace for transparency.
    """
    # --- Attempt 1: real LLM generation (one retry for transient errors) ---
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        for attempt in range(2):
            try:
                import time as _time
                import google.generativeai as genai

                industry = enrichment_data.get("industry", "their industry")
                description = (enrichment_data.get("description") or "")[:300]
                prompt = f"""You are a B2B sales rep writing the FIRST outreach email to an inbound lead.

Lead: {name}, {title or 'job title unknown'} at {company}
Their inquiry: "{message}"
Company context: {industry}. {description}
Lead qualification score: {score}/100 — {score_reason}

Write a short, specific, professional email (80-140 words). Rules:
- Subject line starting with 'Subject:'
- Reference their actual inquiry directly
- One clear call to action (a 15-minute call)
- No invented facts, no fake customer names, no placeholders like [key benefit]
- Sign off as '[Your Name]'"""
                model = genai.GenerativeModel(_EMAIL_MODEL)
                response = model.generate_content(prompt)
                text = (response.text or "").strip()
                if text:
                    return text, "gemini-llm"
            except Exception:
                if attempt == 0:
                    _time.sleep(12)  # brief pause (often a rate limit) and retry once
                continue

    # --- Fallback: deterministic template ---

    # --- Fallback: deterministic template ---
    industry = enrichment_data.get("industry", "your industry")
    company_size = enrichment_data.get("size", "your team size")

    email = f"""Subject: Quick question about {company}'s {industry.lower()} initiatives

Hi {name},

I noticed you reached out about — {message[:120]}{"..." if len(message) > 120 else ""}

Given {company}'s position in {industry.lower()} (team of {company_size}), I think we could help with exactly this kind of challenge.

A few companies similar to yours have seen [key benefit] after working with us — would you be open to a 15-minute call this week to explore whether that makes sense for {company}?

Best,
[Sales Rep Name]
[Company]
"""

    return email.strip(), "template-fallback"
