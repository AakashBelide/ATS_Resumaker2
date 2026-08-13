"use client";
// Tracker (RA.2): jobs you're pursuing, as a filterable + paginated TABLE (most applications
// live in "applied"/"rejected", so a board piles up — a table scales better). Each row shows
// the match outcome (fit / apply / sponsorship), an inline stage editor, and a link to the
// full match report. Resume/cover stay a manual trigger (not wired here yet).
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import Spinner from "@/components/Spinner";

import CompanyLogo from "@/components/CompanyLogo";
import { deleteTracker, listTracker, rematchTracker, setTrackerStage, type TrackerEntry } from "@/lib/api";

const STAGES = ["interested", "applied", "interview", "offer", "rejected", "skipped"];
const PAGE_SIZES = [10, 20, 50];

function fitClass(f: number | null) { return f == null ? "lo" : f >= 65 ? "hi" : f >= 45 ? "mid" : "lo"; }
function fmtDate(iso: string | null) {
  if (!iso) return "—";
  // date + a clean local time, e.g. "Aug 13, 2026, 3:30 PM"
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export default function TrackerPage() {
  const [rows, setRows] = useState<TrackerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
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
  // a failed match (match_error set) is NOT pending — it stops polling and shows a retry.
  const anyPending = rows.some((r) => !r.run_id && r.fit_0_100 == null && !r.match_error);
  useEffect(() => {
    if (!anyPending) return;
    const t = setTimeout(load, 4000);
    return () => clearTimeout(t);
  }, [anyPending, rows, load]);

  async function onStage(id: number, stage: string) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, stage } : r)));  // optimistic
    try { await setTrackerStage(id, stage); } catch (e) { setError(String(e)); load(); }
  }

  async function onRematch(id: number) {
    // optimistic: clear the prior outcome so the row flips back to "matching…" and polling
    // resumes. Works both as a retry (failed match) and a re-run (stale/wrong report).
    setRows((prev) => prev.map((r) => (r.id === id
      ? { ...r, match_error: null, fit_0_100: null, recommend_apply: null, run_id: "" } : r)));
    try { await rematchTracker(id); } catch (e) { setError(String(e)); load(); }
  }

  async function onDelete(id: number, label: string) {
    if (!window.confirm(`Remove "${label}" from the tracker? This can't be undone.`)) return;
    const prev = rows;
    setRows((r) => r.filter((x) => x.id !== id));   // optimistic
    try {
      await deleteTracker(id);
      setNotice(`Removed "${label}" from the tracker.`);
      setTimeout(() => setNotice(""), 4000);
    } catch (e) { setError(String(e)); setRows(prev); }
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

        {loading && <Spinner />}
        {error && <p className="error">{error}</p>}
        {notice && <p className="notice">{notice}</p>}
        {!loading && rows.length === 0 && (
          <div className="empty">Nothing tracked yet. Add jobs from Discovery with “+ Track”.</div>
        )}

        {!loading && rows.length > 0 && (
          <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
            <table className="dtable">
              <thead>
                <tr>
                  <th>Company</th><th>Role</th><th>Location</th><th className="c">Salary</th>
                  <th className="c">Fit</th><th className="c">Decision</th>
                  <th className="c">Sponsorship</th><th>Stage</th><th className="c">Added</th><th className="c">Links</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((e) => {
                  const pending = !e.run_id && e.fit_0_100 == null && !e.match_error;
                  return (
                  <tr key={e.id}>
                    <td>
                      {/* a freshly-captured entry has no company until the match fills it in — show a
                          "matching…" indicator instead of a "?" logo + blank name until it resolves. */}
                      {pending && !e.company ? (
                        <div className="cell-co">
                          <span className="spinner sm" aria-hidden />
                          <span className="matching mono">matching…</span>
                        </div>
                      ) : (
                        <div className="cell-co">
                          <CompanyLogo name={e.company} size={30} />
                          <span>{e.company}</span>
                        </div>
                      )}
                    </td>
                    <td>
                      {/* the role opens the match REPORT (the posting link lives in the Links column) */}
                      {e.run_id ? (
                        <Link className="rolelink" href={`/report/${encodeURIComponent(e.run_id)}`} title={e.title}>
                          {e.title || "(untitled)"}
                        </Link>
                      ) : (
                        <span className="rolelink is-plain" title={e.title}>{e.title || "(untitled)"}</span>
                      )}
                    </td>
                    <td className="mono muted" title={e.location}>{e.location || "—"}</td>
                    <td className="c mono">{e.salary ? <span className="jc-pay">{e.salary}</span> : <span className="muted">—</span>}</td>
                    <td className="c">
                      {e.fit_0_100 != null
                        ? <span className={`fit ${fitClass(e.fit_0_100)}`}>{Math.round(e.fit_0_100)}</span>
                        : e.match_error
                          ? <span className="match-failed" title={e.match_error}>
                              failed
                              <button className="btn btn-sm" onClick={() => e.id != null && onRematch(e.id)}>retry</button>
                            </span>
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
                      <div className="row-actions">
                        {/* icon actions, kept on one line. the report opens from the role. */}
                        <a className="icon-btn" href={e.url} target="_blank" rel="noreferrer" title="open the job posting" aria-label="open the job posting">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><path d="M15 3h6v6M10 14 21 3" /></svg>
                        </a>
                        {!pending && (
                          <button className="icon-btn" title="re-run the match" aria-label="re-run the match"
                                  onClick={() => e.id != null && onRematch(e.id)}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="0.7" fill="currentColor" /></svg>
                          </button>
                        )}
                        <button className="icon-btn danger" title="remove from tracker" aria-label="remove from tracker"
                                onClick={() => e.id != null && onDelete(e.id, e.title || e.company || "this job")}>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6" /></svg>
                        </button>
                      </div>
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
                <input className="page-jump" type="number" min={1} max={pages} placeholder="go"
                       title="go to page" onKeyDown={(ev) => {
                         if (ev.key !== "Enter") return;
                         const v = Number((ev.target as HTMLInputElement).value);
                         if (Number.isFinite(v) && v >= 1) { setPage(Math.min(v, pages) - 1); (ev.target as HTMLInputElement).value = ""; }
                       }} />
                <button className="btn btn-sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>next ›</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
