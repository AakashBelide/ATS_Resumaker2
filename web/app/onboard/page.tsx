"use client";
// Onboarding (RI.0): add a company by name (+ optional careers URL). The backend auto-
// resolves the ATS board (slug-probe -> careers-page parse); unresolved -> supply a URL.
import { useCallback, useEffect, useState } from "react";

import { listCompanies, onboard, type Company, type OnboardResult } from "@/lib/api";

export default function OnboardPage() {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<OnboardResult | null>(null);
  const [error, setError] = useState("");
  const [companies, setCompanies] = useState<Company[]>([]);

  const refresh = useCallback(() => { listCompanies().then(setCompanies).catch(() => {}); }, []);
  useEffect(() => { refresh(); }, [refresh]);

  async function submit() {
    if (!name.trim()) return;
    setBusy(true); setError(""); setRes(null);
    try {
      const r = await onboard(name.trim(), url.trim() || undefined, true);
      setRes(r);
      if (r.resolved) { setName(""); setUrl(""); refresh(); }
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  return (
    <>
      <header className="topbar">
        <div><div className="kicker">Onboarding</div><h1 style={{ marginTop: 6 }}>Add a company</h1></div>
        <div className="topbar-spacer" />
        <span className="mono muted">{companies.length} on watchlist</span>
      </header>

      <div className="page">
        <div className="panel" style={{ maxWidth: 600 }}>
          <div className="form">
            <div>
              <label>Company name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ramp" />
            </div>
            <div>
              <label>Careers URL (optional — helps resolve Workday/custom)</label>
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…/careers" />
            </div>
            <button className="btn btn-primary" onClick={submit} disabled={busy}>
              {busy ? "resolving…" : "Onboard"}
            </button>
          </div>
          {error && <p className="error" style={{ marginTop: 14 }}>{error}</p>}
          {res && (
            <div className={`result ${res.resolved ? "ok" : "no"}`}>
              {res.resolved ? (
                <>
                  <b>Resolved</b> via <span className="mono">{res.method}</span> → {res.boards.map((b) => (
                    <span key={b.source} className="tag" style={{ marginLeft: 6 }}>{b.source}/{b.token}</span>
                  ))}
                  <div className="muted" style={{ marginTop: 6, fontSize: 12.5 }}>Added to the watchlist.</div>
                </>
              ) : (
                <>
                  <b>Unresolved.</b> {res.note}
                  {res.tried.length > 0 && <div className="muted mono" style={{ marginTop: 6, fontSize: 11 }}>tried: {res.tried.join(", ")}</div>}
                  <div className="muted" style={{ marginTop: 6, fontSize: 12.5 }}>Try adding the careers URL above.</div>
                </>
              )}
            </div>
          )}
        </div>

        <div className="block">
          <div className="block-head"><h2>On the watchlist</h2><span className="count">{companies.length}</span></div>
          <div className="chips">
            {companies.map((c) => (
              <span key={c.name} className="chip" title={c.boards.map((b) => `${b.source}/${b.token}`).join(", ")}>
                {c.name} <b>{c.boards[0]?.source ?? "?"}</b>
              </span>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
