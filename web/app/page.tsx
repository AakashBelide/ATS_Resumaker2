"use client";
// Discovery (RA.1): a filterable, deterministic feed of ingested postings. No fit-scoring
// here (that happens on add-to-Tracker); Discovery is pure filtering over the watchlist.
import { useCallback, useEffect, useState } from "react";

import CompanyLogo from "@/components/CompanyLogo";
import { addTracker, discovery, type Discovery, type DiscoveryQuery, type JobRecord } from "@/lib/api";
import { titleLevel } from "@/lib/logo";

const LEVEL_ORDER = ["intern", "junior", "mid", "senior", "staff", "manager"];
const PAGE_SIZES = [24, 48, 96];

function daysAgo(iso: string | null): string {
  if (!iso) return "";
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d <= 0 ? "today" : d === 1 ? "1d ago" : `${d}d ago`;
}

function JobCard({ job, onTrack, tracked, busy }: {
  job: JobRecord; onTrack: (j: JobRecord) => void; tracked: boolean; busy: boolean;
}) {
  const level = titleLevel(job.title);
  return (
    <div className="jobcard">
      <div className="jc-top">
        <CompanyLogo name={job.company} size={42} />
        <div className="jc-head">
          <div className="jc-title" title={job.title}>{job.title}</div>
          <div className="jc-co">{job.company}</div>
        </div>
        {job.status === "new" && <span className="pill new">new</span>}
      </div>
      <div className="jc-meta">
        {job.location ? <span title={job.location}>◍ {job.location}</span> : <span className="muted">◍ location n/a</span>}
      </div>
      <div className="jc-tags">
        <span className={`lvl ${level}`}>{level}</span>
        <span className="tag">{job.source}</span>
        {job.first_seen && <span className="seen">seen {daysAgo(job.first_seen)}</span>}
      </div>
      <div className="jc-foot">
        <a className="btn btn-sm" href={job.url} target="_blank" rel="noreferrer">View JD ↗</a>
        <button className="btn btn-sm btn-primary" onClick={() => onTrack(job)} disabled={busy || tracked}>
          {tracked ? "✓ tracked" : busy ? "…" : "+ Track"}
        </button>
      </div>
    </div>
  );
}

export default function DiscoveryPage() {
  const [q, setQ] = useState<DiscoveryQuery>({ on_target: true, order: "recent", limit: 24, offset: 0 });
  const [data, setData] = useState<Discovery | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tracking, setTracking] = useState<number | null>(null);
  const [tracked, setTracked] = useState<Set<number>>(new Set());

  const load = useCallback(async (query: DiscoveryQuery) => {
    setLoading(true); setError("");
    try { setData(await discovery(query)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(q); }, [q, load]);

  function patch(p: Partial<DiscoveryQuery>) { setQ((prev) => ({ ...prev, ...p, offset: 0 })); }
  function goPage(n: number) { setQ((prev) => ({ ...prev, offset: n * (prev.limit ?? 24) })); }

  async function onTrack(job: JobRecord) {
    if (job.id == null) return;
    setTracking(job.id);
    try {
      await addTracker({ job_id: job.id });
      setTracked((prev) => new Set(prev).add(job.id as number));
    } catch (e) { setError(String(e)); }
    finally { setTracking(null); }
  }

  const limit = q.limit ?? 24;
  const offset = q.offset ?? 0;
  const page = Math.floor(offset / limit);
  const pages = data ? Math.max(1, Math.ceil(data.total / limit)) : 1;
  const from = data && data.total ? offset + 1 : 0;
  const to = data ? Math.min(offset + limit, data.total) : 0;

  const companies = data ? Object.entries(data.facets.companies).sort((a, b) => b[1] - a[1]) : [];
  const companiesAlpha = [...companies].sort((a, b) => a[0].localeCompare(b[0]));  // dropdown: A→Z
  const states = data
    ? Object.entries(data.facets.states).sort((a, b) => (a[0] === "OTHER" ? 1 : b[0] === "OTHER" ? -1 : a[0].localeCompare(b[0])))
    : [];
  const levels = data ? data.facets.levels : {};

  return (
    <>
      <header className="topbar">
        <div>
          <div className="kicker">Discovery</div>
          <h1 style={{ marginTop: 6 }}>New postings</h1>
        </div>
        <div className="topbar-spacer" />
        <span className="mono muted">{data ? `${data.total.toLocaleString()} matches` : ""}</span>
      </header>

      <div className="page">
        <div className="stat-row">
          <div className="stat"><div className="num">{data?.total?.toLocaleString() ?? "—"}</div><div className="cap">Matching postings</div></div>
          <div className="stat"><div className="num accent">{companies.length || "—"}</div><div className="cap">Companies</div></div>
          <div className="stat"><div className="num">{states.filter(([s]) => s !== "OTHER").length || "—"}</div><div className="cap">US states</div></div>
          <div className="stat"><div className="num">{q.on_target ? "ON" : "OFF"}</div><div className="cap">Target-role filter</div></div>
        </div>

        <div className="filters">
          <div className="field">
            <label>kw</label>
            <input placeholder="title keyword" defaultValue={q.keyword ?? ""}
                   onKeyDown={(e) => { if (e.key === "Enter") patch({ keyword: (e.target as HTMLInputElement).value }); }} />
          </div>
          <div className="field">
            <label>loc</label>
            <input placeholder="e.g. boston" defaultValue={q.location ?? ""}
                   onKeyDown={(e) => { if (e.key === "Enter") patch({ location: (e.target as HTMLInputElement).value }); }} />
          </div>
          <div className="field">
            <label>company</label>
            <select value={q.company ?? ""} onChange={(e) => patch({ company: e.target.value || undefined })}>
              <option value="">all</option>
              {companiesAlpha.map(([c, n]) => <option key={c} value={c}>{c} ({n})</option>)}
            </select>
          </div>
          <div className="field">
            <label>state</label>
            <select value={q.state ?? ""} onChange={(e) => patch({ state: e.target.value || undefined })}>
              <option value="">any</option>
              {states.map(([s, n]) => <option key={s} value={s}>{s === "OTHER" ? "Remote / Other" : s} ({n})</option>)}
            </select>
          </div>
          <div className="field">
            <label>level</label>
            <select value={q.level ?? ""} onChange={(e) => patch({ level: e.target.value || undefined })}>
              <option value="">any</option>
              {LEVEL_ORDER.filter((l) => levels[l]).map((l) => <option key={l} value={l}>{l} ({levels[l]})</option>)}
            </select>
          </div>
          <div className="field">
            <label>since</label>
            <select value={q.since_days ?? ""} onChange={(e) => patch({ since_days: e.target.value ? Number(e.target.value) : undefined })}>
              <option value="">any</option><option value="1">1d</option><option value="3">3d</option>
              <option value="7">7d</option><option value="14">14d</option>
            </select>
          </div>
          <div className="field">
            <label>sort</label>
            <select value={q.order} onChange={(e) => patch({ order: e.target.value })}>
              <option value="recent">recent</option><option value="company">company</option><option value="title">title</option>
            </select>
          </div>
          <div className={`field toggle${q.on_target ? " on" : ""}`} onClick={() => patch({ on_target: !q.on_target })}>
            <label>on-target</label><span className="mono">{q.on_target ? "yes" : "no"}</span>
          </div>
        </div>
        <p className="hint">
          <b>On-target</b> keeps only titles that match your <span className="mono">target roles</span> and none of your{" "}
          <span className="mono">avoid roles</span> — a deterministic keyword filter from your Profile, no AI scoring.
          <span className="muted"> Level &amp; state are derived from the title and location text.</span>
        </p>

        {loading && <p className="loading">loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && data && data.jobs.length === 0 && (
          <div className="empty">No postings match these filters.</div>
        )}

        {data && data.jobs.length > 0 && (
          <>
            <div className="cards">
              {data.jobs.map((j) => (
                <JobCard key={`${j.source}:${j.external_id}`} job={j} onTrack={onTrack}
                         tracked={j.id != null && tracked.has(j.id)} busy={tracking === j.id} />
              ))}
            </div>

            <div className="pager">
              <span className="mono muted">{from.toLocaleString()}–{to.toLocaleString()} of {data.total.toLocaleString()}</span>
              <div className="pager-ctrls">
                <select value={limit} onChange={(e) => patch({ limit: Number(e.target.value) })}>
                  {PAGE_SIZES.map((s) => <option key={s} value={s}>{s} / page</option>)}
                </select>
                <button className="btn btn-sm" disabled={page <= 0} onClick={() => goPage(page - 1)}>‹ prev</button>
                <span className="mono">{page + 1} / {pages}</span>
                <button className="btn btn-sm" disabled={page + 1 >= pages} onClick={() => goPage(page + 1)}>next ›</button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
