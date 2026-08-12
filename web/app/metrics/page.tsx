"use client";
// Metrics (RA.5): model calls / cost / usage. Claude CLI usage is logged for visibility
// (subscription, not billed); the Gemini API is hard-capped.
import Link from "next/link";
import { useEffect, useState } from "react";
import Spinner from "@/components/Spinner";

import { listRuns, metrics, type RunRecord } from "@/lib/api";

type Prov = { calls: number; input_tokens: number; output_tokens: number; cost_usd: number };

export default function MetricsPage() {
  const [m, setM] = useState<{ cost: Record<string, any>; runs: any } | null>(null);
  const [runList, setRunList] = useState<RunRecord[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    metrics().then(setM).catch((e) => setError(String(e)));
    listRuns(50).then(setRunList).catch(() => {});
  }, []);

  const cost = m?.cost ?? {};
  const budget = cost._gemini_budget as { cap_usd: number; spent_usd: number; remaining_usd: number } | undefined;
  const providers = Object.entries(cost).filter(([k]) => !k.startsWith("_")) as [string, Prov][];
  const pct = budget && budget.cap_usd ? Math.min(100, (budget.spent_usd / budget.cap_usd) * 100) : 0;
  const totCalls = providers.reduce((a, [, p]) => a + p.calls, 0);
  const totCost = providers.reduce((a, [, p]) => a + p.cost_usd, 0);
  const totTokens = providers.reduce((a, [, p]) => a + p.input_tokens + p.output_tokens, 0);
  const runs = m?.runs;

  const durationS = (r: RunRecord): number | null =>
    r.created_at && r.finished_at
      ? Math.max(0, (new Date(r.finished_at).getTime() - new Date(r.created_at).getTime()) / 1000)
      : null;
  const fmtDur = (s: number | null) =>
    s == null ? "—" : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  const avgDur = (() => {
    const ds = runList.map(durationS).filter((x): x is number => x != null);
    return ds.length ? ds.reduce((a, b) => a + b, 0) / ds.length : null;
  })();

  return (
    <>
      <header className="topbar">
        <div><div className="kicker">Metrics</div><h1 style={{ marginTop: 6 }}>Model usage &amp; cost</h1></div>
      </header>
      <div className="page">
        {error && <p className="error">{error}</p>}
        {!m ? <Spinner /> : (
          <>
            <div className="stat-row">
              <div className="stat"><div className="num accent">${totCost.toFixed(2)}</div><div className="cap">Total spend</div></div>
              <div className="stat"><div className="num">{totCalls.toLocaleString()}</div><div className="cap">LLM calls</div></div>
              <div className="stat"><div className="num">{(totTokens / 1e6).toFixed(2)}M</div><div className="cap">Tokens processed</div></div>
              <div className="stat"><div className="num">{runs?.total ?? 0}</div><div className="cap">Pipeline runs</div></div>
            </div>

            <div className="block">
              <div className="block-head"><h2>LLM usage by provider</h2></div>
              <div className="panel">
                <table className="tbl">
                  <thead><tr><th>Provider</th><th className="num">Calls</th><th className="num">Input tok</th><th className="num">Output tok</th><th className="num">Cost (USD)</th></tr></thead>
                  <tbody>
                    {providers.map(([name, a]) => (
                      <tr key={name}>
                        <td>{name}</td>
                        <td className="num">{a.calls}</td>
                        <td className="num">{a.input_tokens.toLocaleString()}</td>
                        <td className="num">{a.output_tokens.toLocaleString()}</td>
                        <td className="num">${a.cost_usd.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted mono" style={{ fontSize: 11, marginTop: 12 }}>
                  Claude CLI cost = subscription burn (visibility only, not billed per-token).
                </p>
              </div>
            </div>

            {budget && (
              <div className="block">
                <div className="block-head"><h2>Gemini API budget</h2></div>
                <div className="panel">
                  <div className="bar">
                    <span className="lbl">spent</span>
                    <span className="track"><span className="fill" style={{ width: `${pct}%` }} /></span>
                    <span className="val">${budget.spent_usd.toFixed(4)}</span>
                  </div>
                  <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                    ${budget.remaining_usd.toFixed(2)} remaining of ${budget.cap_usd.toFixed(2)} hard cap
                  </p>
                </div>
              </div>
            )}

            <div className="block">
              <div className="block-head"><h2>Pipeline runs</h2></div>
              <div className="panel">
                <div className="chips">
                  <span className="chip">total <b>{m.runs.total}</b></span>
                  {Object.entries(m.runs.by_status ?? {}).map(([k, v]) => (
                    <span key={k} className="chip">{k} <b>{v as number}</b></span>
                  ))}
                  <span className="chip">cost <b>${(m.runs.total_cost_usd ?? 0).toFixed(2)}</b></span>
                  <span className="chip">avg time <b>{fmtDur(avgDur)}</b></span>
                </div>
              </div>
            </div>

            <div className="block">
              <div className="block-head"><h2>Recent runs</h2><span className="count">{runList.length}</span></div>
              <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
                {runList.length === 0 ? <p className="muted" style={{ padding: 20, fontSize: 13 }}>no runs yet</p> : (
                  <table className="dtable">
                    <thead><tr>
                      <th>Run</th><th>Status</th><th className="c">Fit</th><th className="c">Apply</th>
                      <th className="c">Time</th><th className="c">Cost</th><th className="c">Report</th>
                    </tr></thead>
                    <tbody>
                      {runList.map((r) => (
                        <tr key={r.id}>
                          <td className="mono" style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.id}>{r.id}</td>
                          <td><span className="tag">{r.status}</span></td>
                          <td className="c">{r.fit_0_100 != null ? Math.round(r.fit_0_100) : "—"}</td>
                          <td className="c">{r.recommend_apply == null ? "—" : <span className={`pill ${r.recommend_apply ? "apply" : "skip"}`}>{r.recommend_apply ? "apply" : "skip"}</span>}</td>
                          <td className="c mono">{fmtDur(durationS(r))}</td>
                          <td className="c mono">{r.cost_usd ? `$${r.cost_usd.toFixed(2)}` : "—"}</td>
                          <td className="c"><Link className="btn btn-sm" href={`/report/${encodeURIComponent(r.id)}`}>open ↗</Link></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
