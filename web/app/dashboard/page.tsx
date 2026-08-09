"use client";
// Dashboard (RA.4): feed + application-funnel + run outcomes over the watchlist.
import { useEffect, useState } from "react";

import { dashboard, type Dashboard } from "@/lib/api";

function Bars({ data, max }: { data: [string, number][]; max: number }) {
  return (
    <div className="bars">
      {data.map(([label, n]) => (
        <div className="bar" key={label}>
          <span className="lbl">{label}</span>
          <span className="track"><span className="fill" style={{ width: `${max ? (n / max) * 100 : 0}%` }} /></span>
          <span className="val">{n}</span>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [d, setD] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { dashboard(14).then(setD).catch((e) => setError(String(e))); }, []);

  const companies = d ? Object.entries(d.jobs_by_company).slice(0, 12) : [];
  const sources = d ? Object.entries(d.jobs_by_source) : [];
  const daily = d ? [...d.new_listings_daily].reverse() : [];
  const dmax = Math.max(1, ...daily.map((x) => x.count));
  const cmax = Math.max(1, ...companies.map(([, n]) => n));
  const smax = Math.max(1, ...sources.map(([, n]) => n));

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
              <div className="stat"><div className="num accent">{d.watchlist.jobs}</div><div className="cap">Postings ingested</div></div>
              <div className="stat"><div className="num">{d.watchlist.tracked}</div><div className="cap">Tracked</div></div>
              <div className="stat"><div className="num">{d.runs.total}</div><div className="cap">Pipeline runs</div></div>
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
                {Object.keys(d.tracker_funnel).length === 0 ? <p className="muted" style={{ fontSize: 13 }}>no tracked jobs yet</p> :
                  <div className="chips">{Object.entries(d.tracker_funnel).map(([k, v]) => (
                    <span key={k} className={`pill ${k}`}>{k} · {v}</span>))}</div>}
              </div>
            </div>

            <div className="block">
              <div className="block-head"><h2>Postings by company</h2><span className="count">top 12</span></div>
              <div className="panel"><Bars data={companies} max={cmax} /></div>
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
