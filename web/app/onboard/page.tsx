"use client";
// Onboarding (RI.0): add a company by name (+ optional careers URL). The backend auto-
// resolves the ATS board (slug-probe -> careers-page parse); unresolved -> supply a URL.
// The watchlist is grouped by ATS source with per-source counts + a source/text filter so a
// 77-company list stays scannable.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import CompanyLogo from "@/components/CompanyLogo";
import Donut from "@/components/Donut";
import { discovery, getOnboardRun, listCompanies, provideOnboardInput, setCompanyActive, startOnboard, stopOnboard, type Company, type OnboardingRun } from "@/lib/api";

export default function OnboardPage() {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<OnboardingRun | null>(null);
  const [answer, setAnswer] = useState("");
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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

  const poll = useCallback((id: string) => {
    const tick = async () => {
      try {
        const r = await getOnboardRun(id);
        setRun(r);
        if (r.state === "resolved") { setName(""); setUrl(""); refresh(); return; }
        if (r.state === "running") { pollRef.current = setTimeout(tick, 1000); }
        // needs_input / unresolved / killed / stopped / error -> stop polling
      } catch { pollRef.current = setTimeout(tick, 2000); }
    };
    tick();
  }, [refresh]);
  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  async function submit() {
    if (!name.trim()) return;
    if (pollRef.current) clearTimeout(pollRef.current);
    setBusy(true); setError(""); setRun(null);
    try {
      const r = await startOnboard(name.trim(), url.trim() || undefined);
      setRun(r); poll(r.id);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  async function sendAnswer() {
    if (!run || !answer.trim()) return;
    try {
      const r = await provideOnboardInput(run.id, answer.trim());
      setAnswer(""); setRun(r); poll(r.id);
    } catch (e) { setError(String(e)); }
  }

  async function stopRun() {
    if (!run) return;
    if (pollRef.current) clearTimeout(pollRef.current);
    try { setRun(await stopOnboard(run.id)); } catch (e) { setError(String(e)); }
  }

  const running = run?.state === "running";

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
              <button className="btn btn-primary" onClick={submit} disabled={busy || running}>
                {busy || running ? "resolving…" : "Onboard"}
              </button>
            </div>
            {error && <p className="error" style={{ marginTop: 14 }}>{error}</p>}
            {run && (
              <div className={`result ${run.state === "resolved" ? "ok" : ["running", "needs_input"].includes(run.state) ? "" : "no"}`}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <span className="tag">{run.state}</span>
                  <b>{run.name}</b>
                  {run.method && <span className="mono muted" style={{ fontSize: 11.5 }}>via {run.method}</span>}
                  {running && <button className="btn" style={{ marginLeft: "auto" }} onClick={stopRun}>Stop</button>}
                </div>

                {/* live progress timeline */}
                <div className="mono" style={{ fontSize: 11.5, lineHeight: 1.75 }}>
                  {run.events.map((e, i) => (
                    <div key={i} className="muted">
                      <span className="tag" style={{ marginRight: 6 }}>{e.status}</span>
                      {e.stage}{e.detail ? ` — ${e.detail}` : ""}
                    </div>
                  ))}
                </div>

                {run.state === "resolved" && run.board && (
                  <div style={{ marginTop: 8 }}>
                    <b>Resolved</b> → <span className="tag">{run.board.source}/{run.board.token}</span>
                    <div className="muted" style={{ marginTop: 6, fontSize: 12.5 }}>Added to the watchlist and queued for the next ingest.</div>
                  </div>
                )}

                {run.state === "needs_input" && (
                  <div className="panel" style={{ marginTop: 10, padding: 12 }}>
                    <p style={{ margin: "0 0 6px" }}><b>The agent needs your input</b></p>
                    <p className="muted" style={{ margin: "0 0 10px", fontSize: 13 }}>{run.question}</p>
                    <div style={{ display: "flex", gap: 8 }}>
                      <input value={answer} onChange={(e) => setAnswer(e.target.value)}
                             placeholder="careers URL or ATS board token"
                             onKeyDown={(e) => { if (e.key === "Enter") sendAnswer(); }} style={{ flex: 1 }} />
                      <button className="btn btn-primary" onClick={sendAnswer}>Answer</button>
                    </div>
                  </div>
                )}

                {["unresolved", "killed", "stopped", "error"].includes(run.state) && (
                  <div className="muted" style={{ marginTop: 8, fontSize: 12.5 }}>
                    {run.error || run.events[run.events.length - 1]?.detail || run.state}
                    {run.state === "unresolved" && (
                      <div style={{ marginTop: 6 }}>Try adding the careers URL above{run.turns ? ` · ${run.turns} turns · $${run.cost_usd.toFixed(3)}` : ""}.</div>
                    )}
                  </div>
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
