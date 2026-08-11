"use client";
// Onboarding (RI.0): add a company by name (+ optional careers URL). The backend auto-
// resolves the ATS board (slug-probe -> careers-page parse); unresolved -> supply a URL.
// The watchlist is grouped by ATS source with per-source counts + a source/text filter so a
// 77-company list stays scannable.
import { useCallback, useEffect, useMemo, useState } from "react";

import CompanyLogo from "@/components/CompanyLogo";
import Donut from "@/components/Donut";
import { discovery, listCompanies, onboard, setCompanyActive, type Company, type OnboardResult } from "@/lib/api";

export default function OnboardPage() {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<OnboardResult | null>(null);
  const [error, setError] = useState("");
  const [companies, setCompanies] = useState<Company[]>([]);
  const [sourceFilter, setSourceFilter] = useState("");
  const [search, setSearch] = useState("");
  const [postingsBySource, setPostingsBySource] = useState<[string, number][]>([]);

  const refresh = useCallback(() => { listCompanies().then(setCompanies).catch(() => {}); }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    discovery({ limit: 1 })
      .then((d) => setPostingsBySource(Object.entries(d.facets.sources).sort((a, b) => b[1] - a[1])))
      .catch(() => {});
  }, []);

  async function submit() {
    if (!name.trim()) return;
    setBusy(true); setError(""); setRes(null);
    try {
      const r = await onboard(name.trim(), url.trim() || undefined, true);
      setRes(r);
      if (r.resolved) { setName(""); setUrl(""); refresh(); }
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  const srcOf = (c: Company) => c.boards[0]?.source ?? "unresolved";

  async function toggleActive(c: Company) {
    const next = !c.active;
    setCompanies((prev) => prev.map((x) => (x.name === c.name ? { ...x, active: next } : x)));  // optimistic
    try { await setCompanyActive(c.name, next); } catch { refresh(); }
  }

  const bySource = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of companies) m[srcOf(c)] = (m[srcOf(c)] ?? 0) + 1;
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [companies]);

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return companies
      .filter((c) => !sourceFilter || srcOf(c) === sourceFilter)
      .filter((c) => !s || c.name.toLowerCase().includes(s))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [companies, sourceFilter, search]);

  const active = companies.filter((c) => c.active).length;
  const pmax = Math.max(1, ...postingsBySource.map(([, n]) => n));
  const postingsTotal = postingsBySource.reduce((a, [, n]) => a + n, 0);

  return (
    <>
      <header className="topbar">
        <div><div className="kicker">Onboarding</div><h1 style={{ marginTop: 6 }}>Watchlist</h1></div>
        <div className="topbar-spacer" />
        <span className="mono muted">{companies.length} companies · {bySource.length} sources</span>
      </header>

      <div className="page">
        <div className="stat-row">
          <div className="stat"><div className="num">{companies.length}</div><div className="cap">Companies watched</div></div>
          <div className="stat"><div className="num accent">{bySource.length}</div><div className="cap">ATS sources</div></div>
          <div className="stat"><div className="num">{active}</div><div className="cap">In ingest rotation</div></div>
        </div>

        {/* add form */}
        <div className="block">
          <div className="block-head"><h2>Add a company</h2></div>
          <div className="panel" style={{ maxWidth: 640 }}>
            <div className="form" style={{ maxWidth: "none" }}>
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
                    <div className="muted" style={{ marginTop: 6, fontSize: 12.5 }}>Added to the watchlist and queued for the next ingest.</div>
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
        </div>

        {/* composition: source donut (click to cross-filter) + postings-by-source */}
        <div className="block">
          <div className="block-head"><h2>Watchlist composition</h2>
            <span className="count">{companies.length} companies · {postingsTotal.toLocaleString()} postings</span></div>
          <div className="dash-2col">
            <div className="panel donut-panel">
              <p className="kicker" style={{ marginBottom: 8 }}>Companies by source · click to filter</p>
              <Donut data={bySource} unit="companies" active={sourceFilter} size={200}
                     onSlice={(s) => setSourceFilter(sourceFilter === s ? "" : s)} />
            </div>
            <div className="panel">
              <p className="kicker" style={{ marginBottom: 14 }}>Postings ingested by source · top 12</p>
              {postingsBySource.length === 0 ? <p className="muted" style={{ fontSize: 13 }}>—</p> : (
                <div className="bars">
                  {postingsBySource.slice(0, 12).map(([s, n]) => (
                    <div className="bar" key={s}>
                      <span className="lbl">{s}</span>
                      <span className="track"><span className="fill" style={{ width: `${(n / pmax) * 100}%` }} /></span>
                      <span className="val">{n}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* watchlist */}
        <div className="block">
          <div className="block-head"><h2>On the watchlist</h2><span className="count">{filtered.length} shown</span></div>
          <p className="hint" style={{ margin: "0 0 14px" }}>
            Click a company&apos;s status dot to <b>pause</b> or <b>resume</b> its scraping.
            <span className="muted"> Paused companies are skipped by the ingest sweep; resuming picks up live postings from that day on (no backfill).</span>
          </p>

          {sourceFilter && (
            <div className="src-tabs">
              <span className="stab on" onClick={() => setSourceFilter("")}>{sourceFilter}&nbsp;<b>✕</b></span>
              <span className="muted" style={{ fontSize: 12.5, alignSelf: "center" }}>filtering by source — click to clear</span>
            </div>
          )}

          <div className="table-toolbar">
            <input className="search" placeholder="Search companies…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>

          <div className="co-grid">
            {filtered.map((c) => (
              <div className={`co-card${c.active ? "" : " paused"}`} key={c.name}
                   title={c.boards.map((b) => `${b.source}/${b.token}`).join(", ")}>
                <CompanyLogo name={c.name} size={30} />
                <div className="cc-body">
                  <div className="cc-name">{c.name}</div>
                  <div className="cc-src mono">{srcOf(c)}{c.boards.length > 1 ? ` +${c.boards.length - 1}` : ""}</div>
                </div>
                <button className={`dot-btn${c.active ? " on" : ""}`} onClick={() => toggleActive(c)}
                        title={c.active ? "scraping on — click to pause" : "paused — click to resume"}>
                  <span className="dot" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
