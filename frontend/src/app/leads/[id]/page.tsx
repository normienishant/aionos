"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

interface TraceStep {
  step: number;
  tool_called?: string;
  arguments?: Record<string, any>;
  result?: any;
  agent_final_response?: string;
  mode?: string;
}

interface LeadDetail {
  id: string;
  name: string;
  email: string;
  company: string;
  title: string | null;
  message: string;
  created_at: string;
  score: number | null;
  score_reason: string | null;
  decision: string | null;
  enrichment_data: Record<string, any> | null;
  past_interaction_found: boolean;
  generated_email: string | null;
  reasoning_trace: TraceStep[];
}

const DECISION_META: Record<string, { label: string; cls: string }> = {
  "auto-outreach-sent": { label: "Auto-outreach sent", cls: "status-auto" },
  "needs-human-review": { label: "Needs human review", cls: "status-review" },
  "discarded": { label: "Discarded", cls: "status-discard" },
};

const TOOL_LABELS: Record<string, string> = {
  enrich_company: "enrich_company — company lookup",
  check_past_interactions: "check_past_interactions — history check",
  score_lead: "score_lead — ICP scoring",
  draft_outreach_email: "draft_outreach_email — outreach draft",
};

export default function LeadCaseFile() {
  const params = useParams();
  const leadId = params.id as string;
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetch(`/api/leads/${leadId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setLead(d); setState("ready"); })
      .catch(() => setState("error"));
  }, [leadId]);

  async function saveEmail() {
    if (!lead) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/leads/${lead.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ generated_email: draft }),
      });
      if (!res.ok) throw new Error();
      setLead(await res.json());
      setEditing(false);
    } catch {
      alert("Save failed — is the backend running?");
    } finally {
      setSaving(false);
    }
  }

  function copyEmail() {
    if (lead?.generated_email) {
      navigator.clipboard.writeText(lead.generated_email);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }

  if (state === "loading")
    return <div className="py-20 text-center text-stone-400 text-[13px]">Loading case file…</div>;

  if (state === "error" || !lead)
    return (
      <div className="py-20 text-center">
        <p className="text-stone-500 text-[13px] mb-3">Lead not found.</p>
        <Link href="/" className="btn">← Back to pipeline</Link>
      </div>
    );

  const meta = lead.decision ? DECISION_META[lead.decision] : null;
  const scoreTone =
    lead.score === null ? "" : lead.score >= 70 ? "text-green-800" : lead.score >= 40 ? "text-amber-700" : "text-red-700";
  const rubricRows = (lead.score_reason || "").split(" | ").filter(Boolean);

  return (
    <div className="space-y-4">
      <Link href="/" className="text-[12.5px] text-stone-500 hover:text-stone-800 transition-colors inline-block">
        ← Pipeline
      </Link>

      {/* ---- header ---- */}
      <div className="card px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[16px] font-semibold tracking-tight">{lead.name}</h1>
            <div className="text-[12.5px] text-stone-500 mono mt-0.5">{lead.email}</div>
          </div>
          {meta && (
            <span className={`status ${meta.cls} mt-1`}>
              <span className="dot" />{meta.label}
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 mt-4 pt-3 border-t border-stone-100 text-[12.5px]">
          <Fact label="Company" value={lead.company} />
          <Fact label="Title" value={lead.title || "—"} />
          <Fact label="Received" value={new Date(lead.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })} />
          <Fact label="History" value={lead.past_interaction_found ? "Returning" : "New"} />
        </div>
        <div className="mt-3 rounded border border-stone-200 bg-stone-50 px-3.5 py-2.5 text-[12.5px] text-stone-700">
          <span className="text-stone-400 text-[10.5px] uppercase tracking-wide block mb-0.5">Inquiry</span>
          {lead.message}
        </div>
      </div>

      {/* ---- score ---- */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card px-5 py-4 flex flex-col justify-center">
          <div className="text-[10.5px] uppercase tracking-wide text-stone-400">ICP Score</div>
          <div className={`text-[34px] leading-none font-semibold mono mt-1 ${scoreTone}`}>
            {lead.score ?? "—"}
            <span className="text-[13px] text-stone-300 font-normal"> /100</span>
          </div>
        </div>
        <div className="card px-5 py-4 md:col-span-2">
          <div className="text-[10.5px] uppercase tracking-wide text-stone-400 mb-2">Rubric breakdown</div>
          <ul className="space-y-1">
            {rubricRows.map((r, i) => (
              <li key={i} className="flex gap-2 text-[12.5px] text-stone-700">
                <span className="text-stone-300 select-none">·</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ---- enrichment ---- */}
      {lead.enrichment_data && (
        <div className="card px-5 py-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10.5px] uppercase tracking-wide text-stone-400">Company enrichment</div>
            <span className="mono text-[10.5px] text-stone-400">
              source: {String(lead.enrichment_data.enrichment_source || "unknown")}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 text-[12.5px]">
            {Object.entries(lead.enrichment_data)
              .filter(([k]) => k !== "enrichment_source")
              .map(([k, v]) => (
                <Fact key={k} label={k.replace(/_/g, " ")} value={typeof v === "object" ? JSON.stringify(v) : String(v)} />
              ))}
          </div>
        </div>
      )}

      {/* ---- reasoning trace ---- */}
      {lead.reasoning_trace.length > 0 && (
        <div className="card px-5 py-4">
          <div className="flex items-center justify-between mb-4">
            <div className="text-[10.5px] uppercase tracking-wide text-stone-400">Agent reasoning trace</div>
            <span className="mono text-[10.5px] text-stone-400">{lead.reasoning_trace.length} steps</span>
          </div>
          <div>
            {lead.reasoning_trace.map((s, i) => {
              const isFinal = !s.tool_called;
              const isFallback = s.mode === "local-fallback";
              return (
                <div key={i} className={`trace-step ${isFinal ? "trace-final" : ""}`}>
                  <span className="trace-node" />
                  {s.tool_called ? (
                    <>
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <span className="text-[10.5px] text-stone-400 mono">step {s.step}</span>
                        <span className="tool-name">{TOOL_LABELS[s.tool_called] || s.tool_called}</span>
                        {isFallback && (
                          <span className="mono text-[10px] text-amber-700 border border-amber-200 bg-amber-50 rounded px-1">
                            local-fallback
                          </span>
                        )}
                      </div>
                      {s.arguments && Object.keys(s.arguments).length > 0 && (
                        <details className="mt-1">
                          <summary className="text-[11px] text-stone-400 cursor-pointer hover:text-stone-600 select-none">arguments</summary>
                          <pre className="pre-block">{JSON.stringify(s.arguments, null, 2)}</pre>
                        </details>
                      )}
                      {s.result && (
                        <details open={s.tool_called === "score_lead"}>
                          <summary className="text-[11px] text-stone-400 cursor-pointer hover:text-stone-600 select-none">result</summary>
                          <pre className="pre-block">{JSON.stringify(s.result, null, 2)}</pre>
                        </details>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="flex items-baseline gap-2">
                        <span className="text-[10.5px] text-stone-400 mono">step {s.step}</span>
                        <span className="tool-name text-green-800">final decision</span>
                      </div>
                      <pre className="pre-block">{s.agent_final_response}</pre>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ---- outreach email ---- */}
      {lead.generated_email ? (
        <div className="card px-5 py-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10.5px] uppercase tracking-wide text-stone-400">Outreach draft</div>
            <div className="flex gap-2">
              {editing ? (
                <>
                  <button className="btn-primary !py-1" onClick={saveEmail} disabled={saving}>
                    {saving ? "Saving…" : "Save"}
                  </button>
                  <button className="btn !py-1" onClick={() => setEditing(false)}>Cancel</button>
                </>
              ) : (
                <>
                  <button className="btn !py-1" onClick={copyEmail}>{copied ? "Copied" : "Copy"}</button>
                  <button className="btn !py-1" onClick={() => { setDraft(lead.generated_email || ""); setEditing(true); }}>
                    Edit
                  </button>
                </>
              )}
            </div>
          </div>

          {editing ? (
            <textarea
              className="input mono !text-[12.5px] leading-relaxed"
              rows={14}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          ) : (
            <div className="email-doc">{lead.generated_email}</div>
          )}

          {lead.decision === "needs-human-review" && !editing && (
            <p className="notice-review mt-3">
              Suggested draft only — a human must review and approve before anything is sent.
            </p>
          )}
        </div>
      ) : (
        <div className="card px-5 py-4 text-[12.5px] text-stone-500">
          No outreach draft — this lead was routed to <strong>discarded</strong>. The rubric breakdown above records why.
        </div>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10.5px] uppercase tracking-wide text-stone-400">{label}</div>
      <div className="text-stone-800 mt-0.5 break-words">{value}</div>
    </div>
  );
}
