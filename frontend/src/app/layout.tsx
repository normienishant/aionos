import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lead Desk — Sales Qualification Agent",
  description: "Agentic lead qualification and outreach drafting for the sales team",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <div className="max-w-6xl mx-auto px-5 h-12 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="brand-mark">LD</span>
              <span className="text-[13.5px] font-semibold tracking-tight">Lead Desk</span>
              <span className="env-pill">INTERNAL</span>
            </div>
            <nav className="flex items-center gap-5 text-[13px]">
              <a href="/" className="text-stone-600 hover:text-stone-900 transition-colors">Pipeline</a>
              <a href="/submit" className="text-stone-600 hover:text-stone-900 transition-colors">New Lead</a>
            </nav>
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-5 py-6">{children}</main>
        <footer className="max-w-6xl mx-auto px-5 pb-8 pt-2 text-[11px] text-stone-400">
          Lead Desk · agent decisions are logged with full reasoning traces · medium-confidence leads require human approval
        </footer>
      </body>
    </html>
  );
}
