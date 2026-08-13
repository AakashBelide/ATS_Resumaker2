// Landing page (public, `/`). Placeholder for RB.1 — the full YC-style landing lands in RB.2.
// Intentionally minimal for now so the routing/auth restructure can be reviewed on its own.
import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="auth-wrap">
      <div className="auth-card" style={{ alignItems: "center", textAlign: "center" }}>
        <div className="auth-brand">
          <span className="rail-hex" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" />
              <path d="M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z" fill="currentColor" opacity="0.35" stroke="none" />
            </svg>
          </span>
          <b>ATS Resumaker</b>
        </div>
        <h1 style={{ marginTop: 6 }}>Grounded, ATS-optimized job hunting.</h1>
        <p className="muted" style={{ fontSize: 14, lineHeight: 1.6, maxWidth: 440 }}>
          Auto-onboard companies, ingest their postings, triage in one click, and generate a
          fact-checked resume + cover letter — self-hostable and free. (Full landing coming next.)
        </p>
        <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
          <Link className="btn btn-primary" href="/login">Login</Link>
          <Link className="btn" href="/setup">Self-host guide</Link>
        </div>
      </div>
    </main>
  );
}
