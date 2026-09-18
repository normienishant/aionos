"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

// Types
interface TraceStep {
  step: number;
  tool_called?: string;
  arguments?: Record<string, any>;
  result?: any;
  agent_final_response?: string;
  error?: string;
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

// Status badge
function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-gray-400">Pending</span>;

  const styles: Record<string, string> = {
    "auto-outreach-sent": "bg-green-100 text-green-800 border-green-200",
    "needs-human-review": "bg-yellow-100 text-yellow-800 border-yellow-200",
    discarded: "bg-red-100 text-red-800 border-red-200",
  };

  const labels: Record<string, string> = {
    "auto-outreach-sent": "✅ Auto-Outreach Sent",
    "needs-human-review": "⚠️ Needs Human Review",
    discarded: "❌ Discarded",
  };

  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium border ${
        styles[status] || "bg-gray-100"
      }`}
    >
      {labels[status] || status}
    </span>
  );
}

// Tool icon for trace
function ToolIcon({ name }: { name: string }) {
  const icons: Record<string, string> = {
    enrich_company: "🔍",
    check_past_interactions: "📋",
    score_lead: "📊",
    draft_outreach_email: "✉️",
  };
  return <span>{icons[name] || "🔧"}</span>;
}

export default function LeadDetailPage() {
  const params = useParams();
  const leadId = params.id as string;
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedEmail, setCopiedEmail] = useState(false);
  const [editingEmail, setEditingEmail] = useState(false);
  const [emailDraft, setEmailDraft] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);

  async function saveEmail() {
    if (!lead) return;
    setSavingEmail(true);
    try {
      const res = await fetch(`/api/leads/${lead.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ generated_email: emailDraft }),
      });
      if (!res.ok) throw new Error("Failed to save");
      const updated = await res.json();
      setLead(updated);
      setEditingEmail(false);
    } catch (err) {
      console.error(err);
      alert("Could not save the email. Is the backend running?");
    } finally {
      setSavingEmail(false);
    }
  }

  useEffect(() => {
    fetchLead();
  }, [leadId]);

  async function fetchLead() {
    try {
      const res = await fetch(`/api/leads/${leadId}`);
      if (!res.ok) throw new Error("Lead not found");
      const data = await res.json();
      setLead(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function copyEmail() {
    if (lead?.generated_email) {
      navigator.clipboard.writeText(lead.generated_email);
      setCopiedEmail(true);
      setTimeout(() => setCopiedEmail(false), 2000);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-500">Loading lead details...</div>
      </div>
    );
  }

  if (error || !lead) {
    return (
      <div className="text-center py-20">
        <div className="text-gray-500 mb-4">{error || "Lead not found"}</div>
        <Link href="/" className="text-indigo-600 hover:underline">
          ← Back to Dashboard
        </Link>
      </div>
    );
  }

  const scoreColor =
    (lead.score || 0) >= 70
      ? "text-green-600"
      : (lead.score || 0) >= 40
      ? "text-yellow-600"
      : "text-red-600";

  const scoreBg =
    (lead.score || 0) >= 70
      ? "bg-green-50 border-green-200"
      : (lead.score || 0) >= 40
      ? "bg-yellow-50 border-yellow-200"
      : "bg-red-50 border-red-200";

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back link */}
      <Link
        href="/"
        className="text-sm text-gray-500 hover:text-gray-700 inline-flex items-center gap-1"
      >
        ← Back to Dashboard
      </Link>

      {/* Lead header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{lead.name}</h2>
            <p className="text-gray-600">{lead.email}</p>
          </div>
          <StatusBadge status={lead.decision} />
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Company:</span>{" "}
            <span className="font-medium">{lead.company}</span>
          </div>
          <div>
            <span className="text-gray-500">Title:</span>{" "}
            <span className="font-medium">{lead.title || "Not specified"}</span>
          </div>
          <div>
            <span className="text-gray-500">Submitted:</span>{" "}
            <span className="font-medium">
              {new Date(lead.created_at).toLocaleString()}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Past Interactions:</span>{" "}
            <span className="font-medium">
              {lead.past_interaction_found ? "Returning lead" : "New lead"}
            </span>
          </div>
        </div>

        {/* Original message */}
        <div className="mt-4 p-4 bg-gray-50 rounded-lg">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
            Lead Message
          </div>
          <p className="text-sm text-gray-700">{lead.message}</p>
        </div>
      </div>

      {/* Score card */}
      <div className={`rounded-lg border p-6 ${scoreBg}`}>
        <div className="flex items-center gap-4">
          <div className="text-5xl font-bold" style={{ color: "inherit" }}>
            {lead.score}
          </div>
          <div>
            <div className="text-lg font-semibold">Lead Score</div>
            <div className="text-sm opacity-75">out of 100</div>
          </div>
        </div>
        {lead.score_reason && (
          <div className="mt-4 text-sm">
            <div className="font-medium mb-1">Scoring Reasoning:</div>
            <div className="space-y-1">
              {lead.score_reason.split(" | ").map((reason, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-gray-400">•</span>
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Enrichment data */}
      {lead.enrichment_data && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            🔍 Company Enrichment
          </h3>
          <div className="grid grid-cols-2 gap-4">
            {Object.entries(lead.enrichment_data).map(([key, value]) => (
              <div key={key}>
                <div className="text-xs text-gray-500 uppercase tracking-wide">
                  {key.replace(/_/g, " ")}
                </div>
                <div className="font-medium">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reasoning trace */}
      {lead.reasoning_trace.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            🧠 Agent Reasoning Trace
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            Step-by-step of what the agent did and why — this is the full audit
            trail.
          </p>
          <div className="space-y-3 trace-scroll">
            {lead.reasoning_trace.map((step, i) => (
              <div key={i} className="trace-block">
                {step.tool_called ? (
                  <>
                    <div className="flex items-center gap-2 mb-2">
                      <ToolIcon name={step.tool_called} />
                      <span className="font-semibold text-indigo-700">
                        Step {step.step}: {step.tool_called}
                      </span>
                    </div>
                    {step.arguments && (
                      <details className="mb-2">
                        <summary className="text-xs text-gray-500 cursor-pointer">
                          Arguments
                        </summary>
                        <pre className="mt-1 text-xs text-gray-600 overflow-x-auto">
                          {JSON.stringify(step.arguments, null, 2)}
                        </pre>
                      </details>
                    )}
                    {step.result && (
                      <div>
                        <div className="text-xs text-gray-500 mb-1">Result:</div>
                        <pre className="text-xs text-gray-700 overflow-x-auto max-h-40 overflow-y-auto">
                          {JSON.stringify(step.result, null, 2)}
                        </pre>
                      </div>
                    )}
                  </>
                ) : step.agent_final_response ? (
                  <>
                    <div className="font-semibold text-green-700 mb-2">
                      🤖 Agent Final Response
                    </div>
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap">
                      {step.agent_final_response}
                    </pre>
                  </>
                ) : step.error ? (
                  <div className="text-red-600 text-sm">Error: {step.error}</div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Generated email */}
      {lead.generated_email && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              ✉️ Generated Outreach Email
            </h3>
            <div className="flex gap-2">
              {!editingEmail && (
                <>
                  <button
                    onClick={copyEmail}
                    className="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                  >
                    {copiedEmail ? "✓ Copied!" : "Copy"}
                  </button>
                  <button
                    onClick={() => {
                      setEmailDraft(lead.generated_email || "");
                      setEditingEmail(true);
                    }}
                    className="px-3 py-1 text-sm bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded-lg transition-colors"
                  >
                    Edit
                  </button>
                </>
              )}
              {editingEmail && (
                <>
                  <button
                    onClick={saveEmail}
                    disabled={savingEmail}
                    className="px-3 py-1 text-sm bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 rounded-lg transition-colors"
                  >
                    {savingEmail ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={() => setEditingEmail(false)}
                    className="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </>
              )}
            </div>
          </div>
          {editingEmail ? (
            <textarea
              value={emailDraft}
              onChange={(e) => setEmailDraft(e.target.value)}
              rows={14}
              className="w-full px-4 py-3 border border-indigo-300 rounded-lg font-mono text-sm leading-relaxed focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y"
            />
          ) : (
            <div className="email-block">{lead.generated_email}</div>
          )}
          {lead.decision === "needs-human-review" && (
            <p className="mt-3 text-sm text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              ⚠️ This email is a <strong>suggestion only</strong> — a human must
              review and approve before sending.
            </p>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-4">
        <Link
          href="/submit"
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
        >
          + Submit Another Lead
        </Link>
        <Link
          href="/"
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
