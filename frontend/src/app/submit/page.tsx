"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const SAMPLE = {
  name: "Sanjay Kulkarni",
  email: "sanjay.kulkarni@piscesdigital.in",
  company: "Pisces Digital",
  title: "Head of Growth",
  message:
    "We manage performance marketing for D2C brands (team of 35 in Pune). Looking for pricing on an annual plan and a demo for our reporting workflow this week.",
};

export default function NewLeadPage() {
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", company: "", title: "", message: "" });
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(k: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm({ ...form, [k]: e.target.value });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Submission failed");
      router.push(`/leads/${data.id}`);
    } catch (err: any) {
      setError(err?.message || "Something went wrong — is the backend running?");
      setRunning(false);
    }
  }

  return (
    <div className="max-w-xl">
      <h1 className="text-[17px] font-semibold tracking-tight">New Lead</h1>
      <p className="text-[12.5px] text-stone-500 mt-0.5 mb-5">
        The agent enriches the company, checks history, scores against the ICP, and routes the lead.
      </p>

      <form onSubmit={submit} className="card p-5 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="field-label">Full name *</label>
            <input className="input" required value={form.name} onChange={set("name")} placeholder="e.g. Nandini Verma" />
          </div>
          <div>
            <label className="field-label">Work email *</label>
            <input className="input" type="email" required value={form.email} onChange={set("email")} placeholder="name@company.in" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="field-label">Company *</label>
            <input className="input" required value={form.company} onChange={set("company")} placeholder="e.g. Trivadya Health" />
          </div>
          <div>
            <label className="field-label">Title</label>
            <input className="input" value={form.title} onChange={set("title")} placeholder="e.g. VP Operations" />
          </div>
        </div>

        <div>
          <label className="field-label">Inquiry *</label>
          <textarea
            className="input resize-y"
            required
            rows={5}
            value={form.message}
            onChange={set("message")}
            placeholder="Paste the inquiry exactly as received — the agent reads intent keywords from it."
          />
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 text-red-700 px-3 py-2 text-[12.5px]">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button type="submit" className="btn-primary" disabled={running}>
            {running ? "Agent running…" : "Run qualification"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={running}
            onClick={() => setForm(SAMPLE)}
          >
            Fill sample lead
          </button>
          <span className="text-[11.5px] text-stone-400">
            {running ? "typically 10–30s (LLM loop)" : ""}
          </span>
        </div>
      </form>

      <p className="text-[11.5px] text-stone-400 mt-3">
        Routing: score ≥ 70 → outreach drafted &amp; marked sent · 40–69 → suggested draft, human approval required · &lt; 40 → discarded with reason.
      </p>
    </div>
  );
}
