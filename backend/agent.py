"""
The Agent Loop — the heart of the system.

This is NOT a single LLM call. It's a structured multi-step reasoning loop:

  1. LLM receives the lead info + available tools
  2. LLM decides which tool to call first (observe: "enrich company")
  3. We execute the tool, return the result to the LLM
  4. LLM sees the result, decides the next step (observe: "check past interactions")
  5. Repeat until the LLM has all the data it needs
  6. LLM makes a final decision (score → outcome → generate email if needed)

This is what makes it "agentic" — it's not a single prompt/response.
The model autonomously decides the order of operations based on what it learns.
"""

import json
import os
import google.generativeai as genai
from sqlalchemy.orm import Session
from tools import enrich_company, check_past_interactions, score_lead, draft_outreach_email


# ---------------------------------------------------------------------------
# Tool schemas — tell Gemini what functions are available
# These JSON schemas tell the LLM what arguments each tool expects,
# so it can generate structured function calls instead of freeform text.
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "function_declarations": [
            {
                "name": "enrich_company",
                "description": "Look up company data: industry, size, region. Returns mock enrichment data for a given company name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company_name": {
                            "type": "string",
                            "description": "The company name to enrich"
                        }
                    },
                    "required": ["company_name"]
                }
            },
            {
                "name": "check_past_interactions",
                "description": "Check if this email or company has been seen before. Returns whether lead is new or returning.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "Lead email address"
                        },
                        "company_name": {
                            "type": "string",
                            "description": "Lead company name"
                        }
                    },
                    "required": ["email", "company_name"]
                }
            },
            {
                "name": "score_lead",
                "description": "Score a lead 0-100 based on ICP (Ideal Customer Profile) rules. Returns score and reasoning.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Lead name"},
                        "email": {"type": "string", "description": "Lead email"},
                        "company": {"type": "string", "description": "Lead company"},
                        "title": {"type": "string", "description": "Lead job title"},
                        "message": {"type": "string", "description": "Lead inquiry message"},
                        "enrichment_data": {
                            "type": "object",
                            "description": "Enrichment data from enrich_company tool"
                        },
                        "past_interactions": {
                            "type": "object",
                            "description": "Result from check_past_interactions tool"
                        }
                    },
                    "required": ["name", "email", "company", "title", "message", "enrichment_data", "past_interactions"]
                }
            },
            {
                "name": "draft_outreach_email",
                "description": "Draft a personalized outreach email for high-scoring leads.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Lead name"},
                        "company": {"type": "string", "description": "Lead company"},
                        "title": {"type": "string", "description": "Lead job title"},
                        "message": {"type": "string", "description": "Lead inquiry message"},
                        "enrichment_data": {
                            "type": "object",
                            "description": "Enrichment data from enrich_company"
                        },
                        "score": {"type": "integer", "description": "Lead score 0-100"},
                        "score_reason": {"type": "string", "description": "Why the lead got this score"}
                    },
                    "required": ["name", "company", "title", "message", "enrichment_data", "score", "score_reason"]
                }
            },
        ]
    }
]


# ---------------------------------------------------------------------------
# The system prompt — tells the agent HOW to behave
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Sales Lead Qualification Agent. Your job is to evaluate inbound sales leads and decide the best next action.

You have access to these tools:
1. enrich_company — look up company data
2. check_past_interactions — check if lead/email has been seen before
3. score_lead — compute a lead score using ICP rules
4. draft_outreach_email — generate a personalized outreach email

YOUR WORKFLOW:
1. First, call enrich_company to get data about the lead's company
2. Then, call check_past_interactions to see if this is a returning lead
3. Then, call score_lead with all the data you've gathered
4. Based on the score:
   - Score >= 70: call draft_outreach_email, then set decision to "auto-outreach-sent"
   - Score 40-69: call draft_outreach_email, then set decision to "needs-human-review"
   - Score < 40: set decision to "discarded" with the score reason

After completing all tool calls, your FINAL response must be a JSON object with this exact structure:
{
  "decision": "auto-outreach-sent" | "needs-human-review" | "discarded",
  "summary": "One sentence explaining why you made this decision"
}

Call tools in order. Do not skip steps. Do not make the final decision until you have called all relevant tools."""


def run_agent_loop(lead_data: dict, db: Session) -> dict:
    """
    Run the full agentic loop for a new lead.

    This is the core of the system. It:
    1. Initializes the LLM with function-calling tools
    2. Sends the lead data as the initial prompt
    3. Loops: if the model wants to call a tool → execute it → feed result back
    4. When the model gives a final text response (no more tool calls) → parse decision

    Returns the complete result including reasoning trace.

    If GEMINI_API_KEY is not set, falls back to a local pipeline that calls the
    same four tools in the same order — the demo still works end to end, just
    without LLM reasoning (the trace is labeled "local-fallback").
    """
    if not os.getenv("GEMINI_API_KEY"):
        return _run_local_pipeline(lead_data, db, reason="GEMINI_API_KEY not set")

    try:
        return _run_llm_loop(lead_data, db)
    except Exception as e:
        # LLM failed (invalid key, quota, network...) — degrade gracefully so
        # the demo never 500s. The trace notes exactly why.
        return _run_local_pipeline(lead_data, db, reason=f"LLM call failed: {type(e).__name__}: {e}")


def _run_llm_loop(lead_data: dict, db: Session) -> dict:
    """The LLM-driven agent loop using Gemini native function calling."""
    # Model name resolves through the "latest" alias so it keeps working as
    # Google retires old model versions. Default is flash-LITE: the free tier
    # gives it a much larger daily quota than regular flash. Override via LLM_MODEL.
    model = genai.GenerativeModel(
        model_name=os.getenv("LLM_MODEL", "gemini-flash-lite-latest"),
        tools=TOOL_DEFINITIONS,
        system_instruction=SYSTEM_PROMPT,
    )

    chat = model.start_chat(history=[])

    # Build the initial user message with all lead context
    initial_message = f"""New inbound lead to evaluate:

Name: {lead_data['name']}
Email: {lead_data['email']}
Company: {lead_data['company']}
Job Title: {lead_data.get('title', 'Not specified')}
Message: {lead_data['message']}

Please evaluate this lead. Start by calling enrich_company to look up their company data."""

    # The reasoning trace — every step the agent takes, logged here
    reasoning_trace = []
    enriched_data = None
    past_interactions = None
    score_result = None
    generated_email = None

    # ------------------------------------------------------------------
    # The main agent loop: send message → get response → handle tool calls
    # ------------------------------------------------------------------
    current_message = initial_message
    max_iterations = 10  # Safety limit to prevent infinite loops

    for iteration in range(max_iterations):
        response = chat.send_message(current_message)

        # Check if the model wants to call tools
        if response.candidates and response.candidates[0].content:
            parts = response.candidates[0].content.parts
            has_function_call = any(hasattr(part, 'function_call') and part.function_call for part in parts)

            if has_function_call:
                # Execute each tool call and collect results
                tool_results = []

                for part in parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        tool_name = fc.name
                        # Gemini returns args as protobuf structs (MapComposite for
                        # nested objects) — sanitize to plain JSON-safe types first.
                        tool_args = _sanitize(json.loads(json.dumps(dict(fc.args), default=str)))

                        # Execute the actual tool and log it in the trace
                        step_trace = {
                            "step": iteration + 1,
                            "tool_called": tool_name,
                            "arguments": tool_args,
                        }

                        if tool_name == "enrich_company":
                            result = enrich_company(tool_args["company_name"])
                            enriched_data = result
                            step_trace["result"] = result
                            reasoning_trace.append(step_trace)

                        elif tool_name == "check_past_interactions":
                            result = check_past_interactions(
                                tool_args["email"],
                                tool_args["company_name"],
                                db,
                                exclude_lead_id=lead_data.get("id"),
                            )
                            past_interactions = result
                            step_trace["result"] = result
                            reasoning_trace.append(step_trace)

                        elif tool_name == "score_lead":
                            # Pass the data we've already gathered — the orchestrator
                            # holds the authoritative tool results, not the LLM's echo
                            args = dict(tool_args)
                            args["enrichment_data"] = enriched_data or {}
                            args["past_interactions"] = past_interactions or {}
                            result = score_lead(**args)
                            score_result = result
                            step_trace["result"] = result
                            reasoning_trace.append(step_trace)

                        elif tool_name == "draft_outreach_email":
                            args = dict(tool_args)
                            args["enrichment_data"] = enriched_data or {}
                            generated_email, drafted_by = draft_outreach_email(**args)
                            result = {"drafted_by": drafted_by, "email_preview": generated_email[:160] + "..."}
                            step_trace["result"] = result
                            reasoning_trace.append(step_trace)

                        else:
                            step_trace["error"] = f"Unknown tool: {tool_name}"
                            reasoning_trace.append(step_trace)

                        # Build the function response for the LLM
                        # The LLM expects to see the tool result before deciding next
                        tool_results.append(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={"result": result if isinstance(result, dict) else {"text": result}},
                                )
                            )
                        )

                # Send all tool results back to the LLM at once
                current_message = genai.protos.Content(parts=tool_results)

            else:
                # No more tool calls — this is the final response
                final_text = "".join(
                    part.text for part in parts if hasattr(part, 'text') and part.text
                )
                reasoning_trace.append({
                    "step": iteration + 1,
                    "agent_final_response": final_text,
                })

                # Parse the final decision from the LLM's response
                try:
                    # Try to extract JSON from the response
                    decision_data = _parse_json_from_text(final_text)
                    decision = decision_data.get("decision", "needs-human-review")
                except Exception:
                    # Fallback: decide based on score if LLM didn't format correctly
                    decision = _decide_from_score(score_result["score"] if score_result else 0)

                return _build_result(
                    lead_data, enriched_data, past_interactions,
                    score_result, decision, generated_email, reasoning_trace,
                )

    # If we hit the iteration limit, return what we have
    return _build_result(
        lead_data, enriched_data, past_interactions,
        score_result, _decide_from_score(score_result["score"] if score_result else 0),
        generated_email, reasoning_trace,
    )


def _run_local_pipeline(lead_data: dict, db: Session, reason: str = "GEMINI_API_KEY not set") -> dict:
    """
    Fallback pipeline: executes the same four tools in the same order as the
    LLM would, and records the same reasoning-trace shape. Used when the LLM
    is unavailable (no API key, invalid key, quota, network error) so the
    demo still runs end to end.
    """
    trace = []

    enrichment = enrich_company(lead_data["company"])
    trace.append({
        "step": 1, "tool_called": "enrich_company",
        "arguments": {"company_name": lead_data["company"]},
        "result": enrichment, "mode": "local-fallback",
    })

    past = check_past_interactions(
        lead_data["email"], lead_data["company"], db,
        exclude_lead_id=lead_data.get("id"),
    )
    trace.append({
        "step": 2, "tool_called": "check_past_interactions",
        "arguments": {"email": lead_data["email"], "company_name": lead_data["company"]},
        "result": past, "mode": "local-fallback",
    })

    score_result = score_lead(
        lead_data["name"], lead_data["email"], lead_data["company"],
        lead_data.get("title", ""), lead_data["message"], enrichment, past,
    )
    trace.append({
        "step": 3, "tool_called": "score_lead",
        "arguments": {"company": lead_data["company"]},
        "result": score_result, "mode": "local-fallback",
    })

    decision = _decide_from_score(score_result["score"])

    generated_email = None
    if decision in ("auto-outreach-sent", "needs-human-review"):
        generated_email, drafted_by = draft_outreach_email(
            lead_data["name"], lead_data["company"], lead_data.get("title", ""),
            lead_data["message"], enrichment, score_result["score"], score_result["reasoning"],
        )
        trace.append({
            "step": 4, "tool_called": "draft_outreach_email",
            "arguments": {"company": lead_data["company"], "score": score_result["score"]},
            "result": {"drafted_by": drafted_by, "email_preview": generated_email[:160] + "..."},
            "mode": "local-fallback",
        })

    trace.append({
        "step": len(trace) + 1,
        "agent_final_response": json.dumps({
            "decision": decision,
            "summary": f"Local fallback pipeline ({reason}): score {score_result['score']} → {decision}",
        }),
        "mode": "local-fallback",
    })

    return _build_result(
        lead_data, enrichment, past, score_result, decision, generated_email, trace,
    )


def _sanitize(obj):
    """Recursively convert protobuf-ish values (MapComposite etc.) to plain JSON types."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _decide_from_score(score: int) -> str:
    """Fallback decision logic if the LLM doesn't format its response correctly."""
    if score >= 70:
        return "auto-outreach-sent"
    elif score >= 40:
        return "needs-human-review"
    else:
        return "discarded"


def _parse_json_from_text(text: str) -> dict:
    """Extract a JSON object from LLM text that may contain other content."""
    import re
    # Find the first JSON object in the text
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {}


def _build_result(
    lead_data, enriched_data, past_interactions,
    score_result, decision, generated_email, reasoning_trace
) -> dict:
    """Assemble the complete result dictionary."""
    return {
        "lead": lead_data,
        "enrichment_data": enriched_data,
        "past_interactions": past_interactions,
        "score": score_result["score"] if score_result else 0,
        "score_reason": score_result["reasoning"] if score_result else "No scoring performed",
        "decision": decision,
        "generated_email": generated_email,
        "reasoning_trace": reasoning_trace,
    }
