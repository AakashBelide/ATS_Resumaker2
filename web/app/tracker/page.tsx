"use client";
// Tracker (RA.2): jobs you're pursuing, as a filterable + paginated TABLE (most applications
// live in "applied"/"rejected", so a board piles up — a table scales better). Each row shows
// the match outcome (fit / apply / sponsorship), an inline stage editor, and a link to the
// full match report. Resume/cover stay a manual trigger (not wired here yet).
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import CompanyLogo from "@/components/CompanyLogo";
import { listTracker, setTrackerStage, type TrackerEntry } from "@/lib/api";

const STAGES = ["interested", "applied", "interview", "offer", "rejected", "skipped"];
const PAGE_SIZES = [10, 20, 50];

function fitClass(f: number | null) { return f == null ? "lo" : f >= 65 ? "hi" : f >= 45 ? "mid" : "lo"; }
function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function TrackerPage() {
  const [rows, setRows] = useState<TrackerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(10);

  const load = useCallback(async () => {
    setError("");
    try { setRows(await listTracker()); } catch (e) { setError(String(e)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // a freshly-tracked entry's match runs in the background (run_id fills in when done);
  // poll every 4s while any are still matching so fit/decision appear without a manual refresh.
  const anyPending = rows.some((r) => !r.run_id && r.fit_0_100 == null);
  useEffect(() => {
    if (!anyPending) return;
    const t = setTimeout(load, 4000);
    return () => clearTimeout(t);
  }, [anyPending, rows, load]);

  async function onStage(id: number, stage: string) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, stage } : r)));  // optimistic
    try { await setTrackerStage(id, stage); } catch (e) { setError(String(e)); load(); }
  }

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows) c[r.stage] = (c[r.stage] ?? 0) + 1;
    return c;
  }, [rows]);

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return rows
      .filter((r) => !stageFilter || r.stage === stageFilter)
      .filter((r) => !s || r.company.toLowerCase().includes(s) || r.title.toLowerCase().includes(s))
      .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
  }, [rows, search, stageFilter]);

  const pages = Math.max(1, Math.ceil(filtered.length / limit));
  const pageRows = filtered.slice(page * limit, page * limit + limit);
  useEffect(() => { setPage(0); }, [search, stageFilter, limit]);

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
        {/* stage summary chips (click to filter) */}
        <div className="stage-tabs">
          <span className={`stab${stageFilter === "" ? " on" : ""}`} onClick={() => setStageFilter("")}>
            all <b>{rows.length}</b>
          </span>
          {STAGES.map((s) => (
            <span key={s} className={`stab ${s}${stageFilter === s ? " on" : ""}`} onClick={() => setStageFilter(s)}>
              {s} <b>{counts[s] ?? 0}</b>
            </span>
          ))}
        </div>

        <div className="table-toolbar">
          <input className="search" placeholder="Search company or role…" value={search}
                 onChange={(e) => setSearch(e.target.value)} />
        </div>

        {loading && <p className="loading">loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && rows.length === 0 && (
          <div className="empty">Nothing tracked yet. Add jobs from Discovery with “+ Track”.</div>
        )}

        {!loading && rows.length > 0 && (
          <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
            <table className="dtable">
              <thead>
                <tr>
                  <th>Company</th><th>Role</th><th className="c">Fit</th><th className="c">Decision</th>
                  <th className="c">Sponsorship</th><th>Stage</th><th className="c">Added</th><th className="c">Report</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((e) => {
                  const pending = !e.run_id && e.fit_0_100 == null;
                  return (
                  <tr key={e.id}>
                    <td>
                      <div className="cell-co">
                        <CompanyLogo name={e.company} size={30} />
                        <span>{e.company}</span>
                      </div>
                    </td>
                    <td>
                      <a className="rolelink" href={e.url} target="_blank" rel="noreferrer" title={e.title}>
                        {e.title || "(untitled)"}
                      </a>
                    </td>
                    <td className="c">
                      {e.fit_0_100 != null
                        ? <span className={`fit ${fitClass(e.fit_0_100)}`}>{Math.round(e.fit_0_100)}</span>
                        : pending ? <span className="matching mono">matching…</span> : <span className="muted">—</span>}
                    </td>
                    <td className="c">
                      {e.recommend_apply != null
                        ? <span className={`pill ${e.recommend_apply ? "apply" : "skip"}`}>{e.recommend_apply ? "apply" : "skip"}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td className="c">{e.sponsorship ? <span className="tag">{e.sponsorship}</span> : <span className="muted">—</span>}</td>
                    <td>
                      <select className="stage-sel" value={e.stage}
                              onChange={(ev) => e.id != null && onStage(e.id, ev.target.value)}>
                        {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="c mono muted">{fmtDate(e.created_at)}</td>
                    <td className="c">
                      {e.run_id
                        ? <Link className="btn btn-sm" href={`/report/${encodeURIComponent(e.run_id)}`}>open ↗</Link>
                        : <span className="muted">—</span>}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>

            <div className="pager" style={{ padding: "12px 16px" }}>
              <span className="mono muted">
                {filtered.length ? page * limit + 1 : 0}–{Math.min((page + 1) * limit, filtered.length)} of {filtered.length}
              </span>
              <div className="pager-ctrls">
                <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                  {PAGE_SIZES.map((s) => <option key={s} value={s}>{s} / page</option>)}
                </select>
                <button className="btn btn-sm" disabled={page <= 0} onClick={() => setPage(page - 1)}>‹ prev</button>
                <span className="mono">{page + 1} / {pages}</span>
                <button className="btn btn-sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>next ›</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
