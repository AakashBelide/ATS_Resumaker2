"use client";
// Metrics (RA.5): model calls / cost / usage. Claude CLI usage is logged for visibility
// (subscription, not billed); the Gemini API is hard-capped.
import { useEffect, useState } from "react";

import { metrics } from "@/lib/api";

type Prov = { calls: number; input_tokens: number; output_tokens: number; cost_usd: number };

export default function MetricsPage() {
  const [m, setM] = useState<{ cost: Record<string, any>; runs: any } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { metrics().then(setM).catch((e) => setError(String(e))); }, []);

  const cost = m?.cost ?? {};
  const budget = cost._gemini_budget as { cap_usd: number; spent_usd: number; remaining_usd: number } | undefined;
  const providers = Object.entries(cost).filter(([k]) => !k.startsWith("_")) as [string, Prov][];
  const pct = budget && budget.cap_usd ? Math.min(100, (budget.spent_usd / budget.cap_usd) * 100) : 0;

  return (
    <>
      <header className="topbar">
        <div><div className="kicker">Metrics</div><h1 style={{ marginTop: 6 }}>Model usage &amp; cost</h1></div>
      </header>
      <div className="page">
        {error && <p className="error">{error}</p>}
        {!m ? <p className="loading">loading…</p> : (
          <>
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
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
