import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sales Lead Qualification Agent",
  description: "AI-powered lead scoring and outreach automation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          {/* Top navigation bar */}
          <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between items-center h-16">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
                    <span className="text-white font-bold text-sm">LA</span>
                  </div>
                  <h1 className="text-lg font-semibold text-gray-900">
                    Lead Agent
                  </h1>
                  <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-medium">
                    Agentic AI
                  </span>
                </div>
                <nav className="flex items-center gap-4 text-sm">
                  <a href="/" className="text-gray-600 hover:text-gray-900">
                    Dashboard
                  </a>
                  <a href="/submit" className="text-gray-600 hover:text-gray-900">
                    Submit Lead
                  </a>
                </nav>
              </div>
            </div>
          </header>
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
