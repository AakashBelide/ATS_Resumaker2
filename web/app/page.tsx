"use client";
// Discovery (RA.1): a filterable, deterministic feed of ingested postings. No fit-scoring
// here (that happens on add-to-Tracker); Discovery is pure filtering over the watchlist.
import { useCallback, useEffect, useState } from "react";

import { addTracker, discovery, type Discovery, type DiscoveryQuery, type JobRecord } from "@/lib/api";

function daysAgo(iso: string | null): string {
  if (!iso) return "";
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d <= 0 ? "today" : d === 1 ? "1d ago" : `${d}d ago`;
}

function JobCard({ job, onTrack }: { job: JobRecord; onTrack: (j: JobRecord) => void }) {
  return (
    <div className="jobcard">
      <div className="jc-top">
        <div>
          <div className="jc-title">{job.title}</div>
          <div className="jc-co">{job.company}</div>
        </div>
        {job.status === "new" && <span className="pill new" style={{ marginLeft: "auto" }}>new</span>}
      </div>
      <div className="jc-meta">
        {job.location && <span>◍ {job.location}</span>}
        <span className="mono">{job.source}</span>
        {job.first_seen && <span>seen {daysAgo(job.first_seen)}</span>}
      </div>
      <div className="jc-foot">
        <a className="btn btn-sm" href={job.url} target="_blank" rel="noreferrer">View JD ↗</a>
        <button className="btn btn-sm btn-primary" onClick={() => onTrack(job)}>+ Track</button>
      </div>
    </div>
  );
}

export default function DiscoveryPage() {
  const [q, setQ] = useState<DiscoveryQuery>({ on_target: true, order: "recent", limit: 60 });
  const [data, setData] = useState<Discovery | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tracking, setTracking] = useState<number | null>(null);

  const load = useCallback(async (query: DiscoveryQuery) => {
    setLoading(true); setError("");
    try { setData(await discovery(query)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(q); }, [q, load]);

  function patch(p: Partial<DiscoveryQuery>) { setQ((prev) => ({ ...prev, ...p, offset: 0 })); }

  async function onTrack(job: JobRecord) {
    if (job.id == null) return;
    setTracking(job.id);
    try { await addTracker({ job_id: job.id }); }
    catch (e) { setError(String(e)); }
    finally { setTracking(null); }
  }

  const companies = data ? Object.entries(data.facets.companies).sort((a, b) => b[1] - a[1]) : [];

  return (
    <>
      <header className="topbar">
        <div>
          <div className="kicker">Discovery</div>
          <h1 style={{ marginTop: 6 }}>New postings</h1>
        </div>
        <div className="topbar-spacer" />
        <span className="mono muted">{data ? `${data.total} matches` : ""}</span>
      </header>

      <div className="page">
        <div className="stat-row">
          <div className="stat"><div className="num">{data?.total ?? "—"}</div><div className="cap">Matching postings</div></div>
          <div className="stat"><div className="num accent">{companies.length || "—"}</div><div className="cap">Companies</div></div>
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
              {companies.map(([c, n]) => <option key={c} value={c}>{c} ({n})</option>)}
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

        {loading && <p className="loading">loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && data && data.jobs.length === 0 && (
          <div className="empty">No postings match these filters.</div>
        )}

        {data && data.jobs.length > 0 && (
          <div className="cards">
            {data.jobs.map((j) => (
              <div key={`${j.source}:${j.external_id}`} style={{ opacity: tracking === j.id ? 0.5 : 1 }}>
                <JobCard job={j} onTrack={onTrack} />
              </div>
            ))}
          </div>
        )}

        {companies.length > 0 && (
          <div className="chips">
            {companies.slice(0, 16).map(([c, n]) => (
              <span key={c} className="chip" onClick={() => patch({ company: c })}>{c} <b>{n}</b></span>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
