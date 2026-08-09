"use client";
// Dashboard (RA.4): feed + application-funnel + on-target composition over the watchlist.
import { useEffect, useState } from "react";

import CompanyLogo from "@/components/CompanyLogo";
import { dashboard, discovery, type Dashboard, type Discovery } from "@/lib/api";

const LEVEL_ORDER = ["intern", "junior", "mid", "senior", "staff", "manager"];
const STAGE_ORDER = ["interested", "applied", "interview", "offer", "rejected", "skipped"];

function Bars({ data, max, logos }: { data: [string, number][]; max: number; logos?: boolean }) {
  return (
    <div className={`bars${logos ? " with-logos" : ""}`}>
      {data.map(([label, n]) => (
        <div className="bar" key={label}>
          <span className="lbl">{logos && <CompanyLogo name={label} size={22} />}{label}</span>
          <span className="track"><span className="fill" style={{ width: `${max ? (n / max) * 100 : 0}%` }} /></span>
          <span className="val">{n}</span>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [d, setD] = useState<Dashboard | null>(null);
  const [disc, setDisc] = useState<Discovery | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    dashboard(14).then(setD).catch((e) => setError(String(e)));
    discovery({ on_target: true, limit: 1 }).then(setDisc).catch(() => {});
  }, []);

  const companies = d ? Object.entries(d.jobs_by_company).slice(0, 12) : [];
  const sources = d ? Object.entries(d.jobs_by_source) : [];
  const daily = d ? [...d.new_listings_daily].reverse() : [];
  const dmax = Math.max(1, ...daily.map((x) => x.count));
  const cmax = Math.max(1, ...companies.map(([, n]) => n));
  const smax = Math.max(1, ...sources.map(([, n]) => n));

  const levels: [string, number][] = disc
    ? LEVEL_ORDER.filter((l) => disc.facets.levels[l]).map((l) => [l, disc.facets.levels[l]])
    : [];
  const lmax = Math.max(1, ...levels.map(([, n]) => n));
  const states: [string, number][] = disc
    ? Object.entries(disc.facets.states).filter(([s]) => s !== "OTHER").sort((a, b) => b[1] - a[1]).slice(0, 10)
    : [];
  const stmax = Math.max(1, ...states.map(([, n]) => n));

  const funnel = d ? STAGE_ORDER.filter((s) => d.tracker_funnel[s]).map((s) => [s, d.tracker_funnel[s]] as [string, number]) : [];
  const fmax = Math.max(1, ...funnel.map(([, n]) => n));

  return (
    <>
      <header className="topbar">
        <div><div className="kicker">Dashboard</div><h1 style={{ marginTop: 6 }}>Overview</h1></div>
      </header>
      <div className="page">
        {error && <p className="error">{error}</p>}
        {!d ? <p className="loading">loading…</p> : (
          <>
            <div className="stat-row">
              <div className="stat"><div className="num">{d.watchlist.companies}</div><div className="cap">Companies watched</div></div>
              <div className="stat"><div className="num accent">{d.watchlist.jobs.toLocaleString()}</div><div className="cap">Postings ingested</div></div>
              <div className="stat"><div className="num">{disc ? disc.total.toLocaleString() : "—"}</div><div className="cap">On-target postings</div></div>
              <div className="stat"><div className="num">{d.watchlist.tracked}</div><div className="cap">Tracked</div></div>
            </div>

            <div className="block">
              <div className="block-head"><h2>New listings</h2><span className="count">last 14 days</span></div>
              <div className="panel">
                <div className="spark">
                  {daily.map((x) => (
                    <span key={x.date} className={`d${x.date === daily[daily.length - 1]?.date ? " today" : ""}`}
                          style={{ height: `${(x.count / dmax) * 100}%` }} title={`${x.date}: ${x.count}`} />
                  ))}
                </div>
                <div className="spark-x">{daily.map((x) => <span key={x.date}>{x.date.slice(5)}</span>)}</div>
              </div>
            </div>

            <div className="block">
              <div className="block-head"><h2>Application funnel</h2></div>
              <div className="panel">
                {funnel.length === 0 ? <p className="muted" style={{ fontSize: 13 }}>no tracked jobs yet</p> :
                  <div className="bars">
                    {funnel.map(([s, n]) => (
                      <div className="bar" key={s}>
                        <span className="lbl">{s}</span>
                        <span className="track"><span className={`fill stage-${s}`} style={{ width: `${(n / fmax) * 100}%` }} /></span>
                        <span className="val">{n}</span>
                      </div>
                    ))}
                  </div>}
              </div>
            </div>

            <div className="dash-2col">
              <div className="block">
                <div className="block-head"><h2>On-target by level</h2></div>
                <div className="panel">{levels.length ? <Bars data={levels} max={lmax} /> : <p className="muted" style={{ fontSize: 13 }}>—</p>}</div>
              </div>
              <div className="block">
                <div className="block-head"><h2>Top states</h2><span className="count">on-target</span></div>
                <div className="panel">{states.length ? <Bars data={states} max={stmax} /> : <p className="muted" style={{ fontSize: 13 }}>—</p>}</div>
              </div>
            </div>

            <div className="block">
              <div className="block-head"><h2>Postings by company</h2><span className="count">top 12</span></div>
              <div className="panel"><Bars data={companies} max={cmax} logos /></div>
            </div>

            <div className="block">
              <div className="block-head"><h2>By source</h2></div>
              <div className="panel"><Bars data={sources} max={smax} /></div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
