"use client";
// Tracker (RA.2): jobs you're pursuing, as columns by application stage. Each card shows the
// match outcome (fit / apply / sponsorship) and lets you advance the stage. Resume/cover stay
// a manual trigger (not wired here yet).
import { useCallback, useEffect, useState } from "react";

import { artifactUrl, listTracker, setTrackerStage, type TrackerEntry } from "@/lib/api";

const STAGES = ["interested", "applied", "interview", "offer", "rejected", "skipped"];

function fitClass(f: number | null) { return f == null ? "lo" : f >= 65 ? "hi" : f >= 45 ? "mid" : "lo"; }

function Card({ e, onStage }: { e: TrackerEntry; onStage: (id: number, s: string) => void }) {
  return (
    <div className="tcard">
      <div className="t">{e.title || "(untitled)"}</div>
      <div className="co">{e.company}</div>
      <div className="row">
        {e.fit_0_100 != null && <span className={`fit ${fitClass(e.fit_0_100)}`} style={{ marginLeft: 0 }}>{Math.round(e.fit_0_100)}</span>}
        {e.recommend_apply != null && <span className={`pill ${e.recommend_apply ? "apply" : "skip"}`}>{e.recommend_apply ? "apply" : "skip"}</span>}
        {e.sponsorship && <span className="tag">{e.sponsorship}</span>}
      </div>
      <select value={e.stage} onChange={(ev) => e.id != null && onStage(e.id, ev.target.value)}>
        {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      {e.run_id && <a className="match" href={artifactUrl(e.run_id, "report.json")} target="_blank" rel="noreferrer">match report ↗</a>}
    </div>
  );
}

export default function TrackerPage() {
  const [rows, setRows] = useState<TrackerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setRows(await listTracker()); } catch (e) { setError(String(e)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function onStage(id: number, stage: string) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, stage } : r)));  // optimistic
    try { await setTrackerStage(id, stage); } catch (e) { setError(String(e)); load(); }
  }

  const byStage = (s: string) => rows.filter((r) => r.stage === s);

  return (
    <>
      <header className="topbar">
        <div>
          <div className="kicker">Tracker</div>
          <h1 style={{ marginTop: 6 }}>Applications</h1>
        </div>
        <div className="topbar-spacer" />
        <span className="mono muted">{rows.length} tracked</span>
      </header>

      <div className="page">
        {loading && <p className="loading">loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && rows.length === 0 && (
          <div className="empty">Nothing tracked yet. Add jobs from Discovery with “+ Track”.</div>
        )}
        {rows.length > 0 && (
          <div className="board">
            {STAGES.map((s) => {
              const items = byStage(s);
              return (
                <div className="col" key={s}>
                  <div className="col-head"><span className="name">{s}</span><span className="n">{items.length}</span></div>
                  {items.map((e) => <Card key={e.id} e={e} onStage={onStage} />)}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
