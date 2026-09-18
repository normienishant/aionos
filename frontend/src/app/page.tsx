"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Lead {
  id: string;
  name: string;
  email: string;
  company: string;
  title: string | null;
  created_at: string;
  score: number | null;
  decision: string | null;
}

function Status({ decision }: { decision: string | null }) {
  if (!decision) return <span className="status status-pending"><span className="dot" />queued</span>;
  if (decision === "auto-outreach-sent")
    return <span className="status status-auto"><span className="dot" />Auto-outreach</span>;
  if (decision === "needs-human-review")
    return <span className="status status-review"><span className="dot" />Needs review</span>;
  return <span className="status status-discard"><span className="dot" />Discarded</span>;
}

function Score({ score }: { score: number | null }) {
  if (score === null) return <span className="text-stone-300 mono">—</span>;
  const tone =
    score >= 70 ? "text-green-800" : score >= 40 ? "text-amber-700" : "text-red-700";
  return <span className={`mono font-semibold ${tone}`}>{score}</span>;
}

const FILTERS = [
  { key: null as string | null, label: "All leads" },
  { key: "auto-outreach-sent", label: "Auto-outreach" },
  { key: "needs-human-review", label: "Needs review" },
  { key: "discarded", label: "Discarded" },
];

export default function PipelinePage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/leads")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setLeads)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  const counts = {
    total: leads.length,
    auto: leads.filter((l) => l.decision === "auto-outreach-sent").length,
    review: leads.filter((l) => l.decision === "needs-human-review").length,
    discarded: leads.filter((l) => l.decision === "discarded").length,
  };

  const rows = filter ? leads.filter((l) => l.decision === filter) : leads;

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[17px] font-semibold tracking-tight">Pipeline</h1>
          <p className="text-[12.5px] text-stone-500 mt-0.5">
            Inbound leads scored and routed by the qualification agent.
          </p>
        </div>
        <Link href="/submit" className="btn-primary">+ New Lead</Link>
      </div>

      <div className="stat-strip">
        {[
          { label: "Total", n: counts.total, k: null, tone: "text-stone-900" },
          { label: "Auto-outreach", n: counts.auto, k: "auto-outreach-sent", tone: "text-green-800" },
          { label: "Needs review", n: counts.review, k: "needs-human-review", tone: "text-amber-700" },
          { label: "Discarded", n: counts.discarded, k: "discarded", tone: "text-red-700" },
        ].map((s) => (
          <button
            key={s.label}
            className="stat-cell"
            data-active={filter === s.k}
            onClick={() => setFilter(s.k)}
          >
            <div className={`stat-num ${s.tone}`}>{loading ? "·" : s.n}</div>
            <div className="stat-label">{s.label}</div>
          </button>
        ))}
      </div>

      <div className="card overflow-hidden">
        <table className="lead-table">
          <thead>
            <tr>
              <th>Lead</th>
              <th>Company</th>
              <th className="w-20">Score</th>
              <th className="w-40">Decision</th>
              <th className="w-24">Received</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={5} className="py-10 text-center text-stone-400">Loading…</td></tr>
            )}
            {!loading && failed && (
              <tr>
                <td colSpan={5} className="py-10 text-center text-stone-500">
                  Backend not reachable — start it with <code className="mono text-[12px]">python main.py</code> in <code className="mono text-[12px]">backend/</code>, then refresh.
                </td>
              </tr>
            )}
            {!loading && !failed && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="py-10 text-center text-stone-500">
                  No leads here yet. <Link href="/submit" className="text-teal-700 font-medium hover:underline">Submit one →</Link>
                </td>
              </tr>
            )}
            {!loading && !failed && rows.map((l) => (
              <tr key={l.id}>
                <td>
                  <Link href={`/leads/${l.id}`} className="block group">
                    <div className="font-medium text-stone-900 group-hover:text-teal-800 transition-colors">{l.name}</div>
                    <div className="text-[12px] text-stone-500 mono">{l.email}</div>
                  </Link>
                </td>
                <td>
                  <div className="text-stone-800">{l.company}</div>
                  {l.title && <div className="text-[12px] text-stone-500">{l.title}</div>}
                </td>
                <td><Score score={l.score} /></td>
                <td><Status decision={l.decision} /></td>
                <td className="text-[12px] text-stone-500 mono">
                  {new Date(l.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[11.5px] text-stone-400">
        Scoring rubric: company size · industry fit · inquiry intent · history · email domain · seniority — every factor is logged per lead.
      </p>
    </div>
  );
}
