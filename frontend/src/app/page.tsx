"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

// Types
interface Lead {
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
}

// Status badge component
function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-gray-400 text-sm">Pending</span>;

  const styles: Record<string, string> = {
    "auto-outreach-sent": "bg-green-100 text-green-800 border-green-200",
    "needs-human-review": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "discarded": "bg-red-100 text-red-800 border-red-200",
  };

  const labels: Record<string, string> = {
    "auto-outreach-sent": "Auto-Outreach Sent",
    "needs-human-review": "Needs Review",
    "discarded": "Discarded",
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${
        styles[status] || "bg-gray-100 text-gray-800"
      }`}
    >
      {labels[status] || status}
    </span>
  );
}

// Score display with color coding
function ScoreDisplay({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-400">—</span>;

  const color =
    score >= 70 ? "text-green-600" : score >= 40 ? "text-yellow-600" : "text-red-600";

  return (
    <span className={`font-bold ${color}`}>{score}</span>
  );
}

export default function Dashboard() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string | null>(null);

  useEffect(() => {
    fetchLeads();
  }, []);

  async function fetchLeads() {
    try {
      const res = await fetch("/api/leads");
      const data = await res.json();
      setLeads(data);
    } catch (err) {
      console.error("Failed to fetch leads:", err);
    } finally {
      setLoading(false);
    }
  }

  const filteredLeads = filter
    ? leads.filter((l) => l.decision === filter)
    : leads;

  // Count by status
  const counts = {
    total: leads.length,
    auto: leads.filter((l) => l.decision === "auto-outreach-sent").length,
    review: leads.filter((l) => l.decision === "needs-human-review").length,
    discarded: leads.filter((l) => l.decision === "discarded").length,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-500">Loading leads...</div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">
          Lead Dashboard
        </h2>
        <p className="text-gray-600">
          All inbound leads, scored and decided by the AI agent.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <SummaryCard
          label="Total Leads"
          count={counts.total}
          color="text-gray-900"
          onClick={() => setFilter(null)}
          active={filter === null}
        />
        <SummaryCard
          label="Auto-Outreach"
          count={counts.auto}
          color="text-green-600"
          onClick={() => setFilter("auto-outreach-sent")}
          active={filter === "auto-outreach-sent"}
        />
        <SummaryCard
          label="Needs Review"
          count={counts.review}
          color="text-yellow-600"
          onClick={() => setFilter("needs-human-review")}
          active={filter === "needs-human-review"}
        />
        <SummaryCard
          label="Discarded"
          count={counts.discarded}
          color="text-red-600"
          onClick={() => setFilter("discarded")}
          active={filter === "discarded"}
        />
      </div>

      {/* Leads table */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Lead
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Company
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Score
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Created
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {filteredLeads.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                  No leads found.{" "}
                  <Link href="/submit" className="text-indigo-600 hover:underline">
                    Submit one →
                  </Link>
                </td>
              </tr>
            ) : (
              filteredLeads.map((lead) => (
                <tr key={lead.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <Link href={`/leads/${lead.id}`} className="block">
                      <div className="font-medium text-gray-900 hover:text-indigo-600">
                        {lead.name}
                      </div>
                      <div className="text-sm text-gray-500">{lead.email}</div>
                    </Link>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900">{lead.company}</div>
                    {lead.title && (
                      <div className="text-xs text-gray-500">{lead.title}</div>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <ScoreDisplay score={lead.score} />
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={lead.decision} />
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {new Date(lead.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Quick link */}
      <div className="mt-6 text-center">
        <Link
          href="/submit"
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
        >
          + Submit New Lead
        </Link>
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  count,
  color,
  onClick,
  active,
}: {
  label: string;
  count: number;
  color: string;
  onClick: () => void;
  active: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`p-4 rounded-lg border text-left transition-all ${
        active
          ? "border-indigo-300 bg-indigo-50 ring-1 ring-indigo-200"
          : "border-gray-200 bg-white hover:border-gray-300"
      }`}
    >
      <div className={`text-2xl font-bold ${color}`}>{count}</div>
      <div className="text-sm text-gray-600 mt-1">{label}</div>
    </button>
  );
}
