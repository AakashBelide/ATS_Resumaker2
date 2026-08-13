"use client";
// Login page (RB.1). Posts to /api/login; on success the server sets the session cookie and we go
// to the requested page (?next=…) or the dashboard. No client-side auth state — the httpOnly cookie
// + middleware are the source of truth, so there's nothing to bypass here.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const r = await fetch("/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (r.ok) {
        const next = new URLSearchParams(window.location.search).get("next");
        router.push(next && next.startsWith("/") ? next : "/discovery");
        router.refresh();
      } else {
        const j = await r.json().catch(() => ({}));
        setError(j.error || "login failed");
      }
    } catch { setError("could not reach the server"); }
    finally { setBusy(false); }
  }

  return (
    <main className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="auth-brand">
          <span className="rail-hex" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" />
              <path d="M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z" fill="currentColor" opacity="0.35" stroke="none" />
            </svg>
          </span>
          <b>ATS Resumaker</b>
        </div>
        <h1>Sign in</h1>
        <p className="muted" style={{ fontSize: 13, marginTop: 2 }}>Enter your credentials to open the dashboard.</p>

        <label className="auth-field">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus />
        </label>
        <label className="auth-field">
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>

        {error && <p className="error" style={{ marginTop: 4 }}>{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy || !username || !password}>
          {busy ? "signing in…" : "Sign in"}
        </button>
        <Link className="auth-alt mono" href="/">← back to home</Link>
      </form>
    </main>
  );
}
