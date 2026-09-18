"""
Agent tool functions.

These are the four distinct tools the LLM agent can invoke via function calling.
Each is a standalone Python function that could be swapped for a real API call
in production — right now they use mock data or local DB queries.
"""

import json
from sqlalchemy.orm import Session
from models import Lead, LeadDecision


def enrich_company(company_name: str) -> dict:
    """
    TOOL: enrich_company
    Given a company name, return simulated enrichment data.
    
    In production, this would call Clearbit, Apollo, or similar.
    Here we generate realistic mock data based on the company name to make
    the demo convincing.
    """
    # Deterministic mock enrichment based on company name hash
    # This ensures the same company always gets the same data
    name_lower = company_name.lower().strip()
    name_hash = sum(ord(c) for c in name_lower)

    industries = [
        "SaaS / Enterprise Software",
        "FinTech",
        "HealthTech",
        "E-Commerce / Retail",
        "Manufacturing",
        "Consulting / Professional Services",
        "EdTech",
        "Logistics / Supply Chain",
    ]
    regions = ["North America", "Europe", "APAC", "LATAM", "Middle East", "India / South Asia"]
    sizes = ["1-10 (Startup)", "11-50 (Small)", "51-200 (Mid-size)", "201-1000 (Large)", "1000+ (Enterprise)"]

    # Simulate some well-known companies with better data
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
        # Long company names trend toward larger/established orgs; short names
        # trend toward small businesses. Keeps the demo narrative coherent.
        # Non-corporate names (local shops, freelance businesses) get small-business
        # enrichment + a non-corporate industry so scoring penalizes them naturally.
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

        # Company names usually reflect the industry ("Global Finance Partners"
        # → FinTech, "TechCorp Solutions" → SaaS) — use name markers for a
        # sensible industry pick, falling back to a hash for unknown names.
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
            # Non-corporate industries map to low ICP relevance
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
        "enrichment_source": "mock_enrichment_v1",
    }


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
    high_value_industries = ["saas", "enterprise", "fintech", "cloud", "consulting", "technology"]
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
) -> str:
    """
    TOOL: draft_outreach_email
    Generate a personalized first outreach email for high-scoring leads.

    In production, this would be an LLM call. Here we template it with
    personalization from the lead data — clean enough to demo and explain.
    """
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

    return email.strip()
