"use client";
// Discovery (RA.1): a filterable, deterministic feed of ingested postings. No fit-scoring
// here (that happens on add-to-Tracker); Discovery is pure filtering over the watchlist.
import { useCallback, useEffect, useState } from "react";
import Spinner from "@/components/Spinner";

import CompanyLogo from "@/components/CompanyLogo";
import MultiSelect from "@/components/MultiSelect";
import Select from "@/components/Select";
import {
  addTracker, discovery, listTracker, type Discovery, type DiscoveryQuery, type JobRecord,
} from "@/lib/api";
import { titleLevel, workModel } from "@/lib/logo";

const LEVEL_ORDER = ["intern", "junior", "mid", "senior", "staff", "manager"];
const PAGE_SIZES = [24, 48, 96];
const STORE_KEY = "discovery.q";
// Defaults applied on EVERY load (not persisted): recent postings from the last day, junior/mid
// level. These two are re-forced on mount even if a prior session's filters were saved.
const DEFAULT_LEVELS = ["junior", "mid"];
const DEFAULT_Q: DiscoveryQuery = { on_target: true, order: "recent", limit: 24, offset: 0, since_days: 1, level: DEFAULT_LEVELS };

// Exact local date-time we first fetched the posting (replaces the vague "today / Nd ago").
function fmtSeen(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function JobCard({ job, onTrack, tracked, busy }: {
  job: JobRecord; onTrack: (j: JobRecord) => void; tracked: boolean; busy: boolean;
}) {
  const level = titleLevel(job.title);
  const wm = workModel(job.location);
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
        {job.comp && <span className="jc-pay" title="pay stated by the employer">{job.comp}</span>}
      </div>
      <div className="jc-tags">
        <span className={`lvl ${level}`}>{level}</span>
        {wm && <span className={`wm ${wm}`}>{wm}</span>}
        <span className="tag">{job.source}</span>
        {job.first_seen && <span className="seen" title="when we first fetched this posting">seen {fmtSeen(job.first_seen)}</span>}
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
  const [q, setQ] = useState<DiscoveryQuery>(DEFAULT_Q);
  const [restored, setRestored] = useState(false);
  const [data, setData] = useState<Discovery | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tracking, setTracking] = useState<number | null>(null);
  const [tracked, setTracked] = useState<Set<string>>(new Set());  // tracked job URLs
  const [kw, setKw] = useState("");
  const [titleInc, setTitleInc] = useState("");   // title has any of (comma-separated)
  const [titleExc, setTitleExc] = useState("");   // title has none of (comma-separated)

  // restore persisted filters once on mount (survives nav to/from other pages)
  useEffect(() => {
    try {
      const s = sessionStorage.getItem(STORE_KEY);
      if (s) {
        // Restore the session's filters AS-IS so a change survives navigating away and back. The
        // 1-day + junior/mid defaults (DEFAULT_Q) only apply on a fresh landing (no saved state).
        const parsed = JSON.parse(s) as DiscoveryQuery;
        setQ(parsed); setKw(parsed.keyword ?? "");
        setTitleInc((parsed.title_include ?? []).join(", "));
        setTitleExc((parsed.title_exclude ?? []).join(", "));
      }
    } catch { /* ignore */ }
    setRestored(true);
    listTracker().then((rows) => setTracked(new Set(rows.map((r) => r.url)))).catch(() => {});
  }, []);

  const load = useCallback(async (query: DiscoveryQuery) => {
    setLoading(true); setError("");
    try { setData(await discovery(query)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!restored) return;
    sessionStorage.setItem(STORE_KEY, JSON.stringify(q));
    load(q);
  }, [q, restored, load]);

  // debounce the keyword box -> query
  useEffect(() => {
    if (!restored) return;
    const t = setTimeout(() => { if ((q.keyword ?? "") !== kw) patch({ keyword: kw || undefined }); }, 350);
    return () => clearTimeout(t);
  }, [kw]);  // eslint-disable-line react-hooks/exhaustive-deps

  // debounce the title has/no boxes -> query (comma-separated -> array)
  useEffect(() => {
    if (!restored) return;
    const csv = (s: string) => { const a = s.split(",").map((x) => x.trim()).filter(Boolean); return a.length ? a : undefined; };
    const t = setTimeout(() => patch({ title_include: csv(titleInc), title_exclude: csv(titleExc) }), 400);
    return () => clearTimeout(t);
  }, [titleInc, titleExc]);  // eslint-disable-line react-hooks/exhaustive-deps

  function patch(p: Partial<DiscoveryQuery>) { setQ((prev) => ({ ...prev, ...p, offset: 0 })); }
  function goPage(n: number) { setQ((prev) => ({ ...prev, offset: n * (prev.limit ?? 24) })); }
  function clearFilters() {
    setKw(""); setTitleInc(""); setTitleExc("");
    setQ((prev) => ({ order: prev.order, limit: prev.limit, on_target: prev.on_target, offset: 0 }));
  }

  async function onTrack(job: JobRecord) {
    if (job.id == null) return;
    setTracking(job.id);
    try {
      await addTracker({ job_id: job.id });     // instant add; match runs in the background
      setTracked((prev) => new Set(prev).add(job.url));
    } catch (e) { setError(String(e)); }
    finally { setTracking(null); }
  }

  const limit = q.limit ?? 24;
  const offset = q.offset ?? 0;
  const page = Math.floor(offset / limit);
  const pages = data ? Math.max(1, Math.ceil(data.total / limit)) : 1;
  const from = data && data.total ? offset + 1 : 0;
  const to = data ? Math.min(offset + limit, data.total) : 0;

  const companyOpts = data
    ? Object.entries(data.facets.companies).sort((a, b) => a[0].localeCompare(b[0])) as [string, number][]
    : [];
  const stateOpts = data
    ? (Object.entries(data.facets.states) as [string, number][])
        .sort((a, b) => (a[0] === "OTHER" ? 1 : b[0] === "OTHER" ? -1 : a[0].localeCompare(b[0])))
    : [];
  const levelOpts = data
    ? LEVEL_ORDER.filter((l) => data.facets.levels[l]).map((l) => [l, data.facets.levels[l]] as [string, number])
    : [];

  const activeFilters =
    (q.company?.length ?? 0) + (q.state?.length ?? 0) + (q.level?.length ?? 0) +
    (q.keyword ? 1 : 0) + (q.location ? 1 : 0) + (q.since_days ? 1 : 0) +
    (q.title_include?.length ? 1 : 0) + (q.title_exclude?.length ? 1 : 0);

  return (
    <>
      <header className="topbar">
        <div>
          <div className="kicker">Discovery</div>
          <h1 style={{ marginTop: 6 }}>New postings</h1>
        </div>
        <div className="topbar-spacer" />
        {/* the total also lives in the "Matching postings" stat card below, so it's not repeated here */}
      </header>

      <div className="page">
        <div className="stat-row">
          <div className="stat"><div className="num">{data?.total?.toLocaleString() ?? "—"}</div><div className="cap">Matching postings</div></div>
          <div className="stat"><div className="num accent">{companyOpts.length || "—"}</div><div className="cap">Companies</div></div>
          <div className="stat"><div className="num">{stateOpts.filter(([s]) => s !== "OTHER").length || "—"}</div><div className="cap">US states</div></div>
          <div className="stat"><div className="num">{q.on_target ? "ON" : "OFF"}</div><div className="cap">Target-role filter</div></div>
        </div>

        <div className="filters">
          <div className="field">
            <label>kw</label>
            <input placeholder="title or company" value={kw} onChange={(e) => setKw(e.target.value)} />
          </div>
          <div className="field">
            <label>loc</label>
            <input placeholder="e.g. boston" defaultValue={q.location ?? ""}
                   onKeyDown={(e) => { if (e.key === "Enter") patch({ location: (e.target as HTMLInputElement).value || undefined }); }} />
          </div>
          <div className="field">
            <label>title has</label>
            <input placeholder="ai, ml (any)" value={titleInc} onChange={(e) => setTitleInc(e.target.value)} />
          </div>
          <div className="field">
            <label>title no</label>
            <input placeholder="java, manager" value={titleExc} onChange={(e) => setTitleExc(e.target.value)} />
          </div>
          <MultiSelect label="company" options={companyOpts} selected={q.company ?? []} onChange={(v) => patch({ company: v })} />
          <MultiSelect label="state" options={stateOpts} selected={q.state ?? []} onChange={(v) => patch({ state: v })}
                       labelFor={(v) => (v === "OTHER" ? "Remote / Other" : v)} />
          <MultiSelect label="level" options={levelOpts} selected={q.level ?? []} onChange={(v) => patch({ level: v })} />
          <Select label="since" value={String(q.since_days ?? "")}
                  options={[{ value: "", label: "any" }, { value: "1", label: "1d" }, { value: "3", label: "3d" },
                            { value: "7", label: "7d" }, { value: "14", label: "14d" }]}
                  onChange={(v) => patch({ since_days: v ? Number(v) : undefined })} />
          <Select label="sort" value={q.order ?? "recent"}
                  options={[{ value: "recent", label: "recent" }, { value: "company", label: "company" }, { value: "title", label: "title" }]}
                  onChange={(v) => patch({ order: v })} />
          <div className={`field toggle${q.on_target ? " on" : ""}`} onClick={() => patch({ on_target: !q.on_target })}>
            <label>on-target</label><span className="mono">{q.on_target ? "yes" : "no"}</span>
          </div>
          {activeFilters > 0 && (
            <button className="btn btn-sm clear-btn" onClick={clearFilters}>✕ clear {activeFilters}</button>
          )}
        </div>
        <p className="hint">
          <b>On-target</b> keeps titles in your field (engineer / AI / ML / data / software / analyst / scientist …) and drops your{" "}
          <span className="mono">avoid roles</span> — a deterministic keyword filter, no AI scoring.
          <span className="muted"> Recency = when we first fetched it. Level &amp; state are derived from the title/location.</span>
        </p>

        {loading && <Spinner />}
        {error && <p className="error">{error}</p>}
        {!loading && data && data.jobs.length === 0 && (
          <div className="empty">No postings match these filters.</div>
        )}

        {data && data.jobs.length > 0 && (
          <>
            <div className="cards">
              {data.jobs.map((j) => (
                <JobCard key={`${j.source}:${j.external_id}`} job={j} onTrack={onTrack}
                         tracked={tracked.has(j.url)} busy={tracking === j.id} />
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
                {/* jump straight to a page number (clamped to 1..pages) */}
                <input className="page-jump" type="number" min={1} max={pages} placeholder="go"
                       title="go to page" onKeyDown={(e) => {
                         if (e.key !== "Enter") return;
                         const v = Number((e.target as HTMLInputElement).value);
                         if (Number.isFinite(v) && v >= 1) { goPage(Math.min(v, pages) - 1); (e.target as HTMLInputElement).value = ""; }
                       }} />
                <button className="btn btn-sm" disabled={page + 1 >= pages} onClick={() => goPage(page + 1)}>next ›</button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
