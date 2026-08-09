"use client";
// Match-report detail: renders outputs/<run_id>/report.json as a readable analysis instead
// of raw JSON. Its own route (linked from the Tracker). Match-only runs have no resume/ATS
// sections, so those are shown only when present.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import CompanyLogo from "@/components/CompanyLogo";
import { artifactUrl, getReport, getRun, startRun, subscribe, type Report } from "@/lib/api";

function scoreColor(v: number) { return v >= 65 ? "hi" : v >= 45 ? "mid" : "lo"; }
function pct(v: number) { return Math.round(v <= 1 ? v * 100 : v); }

function Meter({ label, value }: { label: string; value: number }) {
  const p = pct(value);
  return (
    <div className="bar">
      <span className="lbl">{label}</span>
      <span className="track"><span className="fill" style={{ width: `${p}%` }} /></span>
      <span className="val">{p}</span>
    </div>
  );
}

const GAP_GROUPS: { key: string; label: string; cls: string }[] = [
  { key: "gap", label: "Gaps", cls: "gap" },
  { key: "supportedByResume", label: "Supported by resume", cls: "have" },
  { key: "existing", label: "Already have", cls: "existing" },
];

export default function ReportPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [r, setR] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [gen, setGen] = useState<{ stage: string } | null>(null);   // in-progress generation
  const [genDone, setGenDone] = useState<string | null>(null);       // new run id when done

  const load = useCallback(() => {
    setError("");
    getReport(runId).then(setR).catch((e) => setError(String(e)));
  }, [runId]);
  useEffect(() => { load(); }, [load]);

  async function generate() {
    if (!r) return;
    setGen({ stage: "starting" }); setGenDone(null); setError("");
    try {
      const { run_id } = await startRun(r.url);
      const unsub = subscribe(run_id, (stage, status) => setGen({ stage: `${stage} · ${status}` }));
      const poll = setInterval(async () => {
        try {
          const rec = await getRun(run_id);
          if (["done", "error", "matched"].includes(rec.status)) {
            clearInterval(poll); unsub(); setGen(null); setGenDone(run_id);
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e) { setError(String(e)); setGen(null); }
  }

  return (
    <>
      <header className="topbar">
        <div>
          <div className="kicker">Match report</div>
          <h1 style={{ marginTop: 6 }}>{r ? r.job.title : "…"}</h1>
        </div>
        <div className="topbar-spacer" />
        <Link className="btn btn-sm" href="/tracker">‹ back to tracker</Link>
      </header>

      <div className="page">
        {error && (
          <div className="empty" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
            <span className="error">{error}</span>
            <span className="muted" style={{ fontSize: 12.5 }}>The API may have just restarted. Try again.</span>
            <button className="btn btn-sm btn-primary" onClick={load}>retry</button>
          </div>
        )}
        {!r && !error && <p className="loading">loading…</p>}
        {r && (
          <div className="report-grid">
            {/* -------- left: analysis -------- */}
            <div className="report-main">
              <div className="report-head">
                <CompanyLogo name={r.job.company} size={52} />
                <div>
                  <div className="rh-co">{r.job.company}</div>
                  <div className="rh-meta">
                    {r.job.source_type && <span className="tag">{r.job.source_type}</span>}
                    <a className="mono" href={r.url} target="_blank" rel="noreferrer">open posting ↗</a>
                  </div>
                </div>
              </div>

              <div className="pills-row">
                {r.job.location && <span className="mpill">◍ {r.job.location}</span>}
                {r.job.work_model && <span className="mpill">◆ {r.job.work_model}</span>}
                {r.job.seniority && <span className="mpill">▲ {r.job.seniority}</span>}
                {r.job.salary_range && <span className="mpill money">$ {r.job.salary_range}</span>}
                {r.job.sponsorship_stance && <span className="mpill">✦ sponsorship: {r.job.sponsorship_stance}</span>}
              </div>

              {/* fit */}
              <div className="block">
                <div className="block-head"><h2>Fit</h2></div>
                <div className="panel">
                  <div className="fit-lead">
                    <div className={`fit-score ${scoreColor(r.fit.final_0_100)}`}>{Math.round(r.fit.final_0_100)}<small>/100</small></div>
                    <div className="fit-sub">
                      <div className="mono muted">
                        rule-based {Math.round(r.fit.deterministic_0_100)}/100 · AI-judged {Math.round(r.fit.llm_0_100)}/100
                      </div>
                      <p>{r.fit.rationale}</p>
                    </div>
                  </div>
                  <div className="bars" style={{ marginTop: 16 }}>
                    {Object.entries(r.fit.dimensions).map(([k, v]) => <Meter key={k} label={k} value={v} />)}
                  </div>
                </div>
              </div>

              {/* decision */}
              <div className="block">
                <div className="block-head">
                  <h2>Decision</h2>
                  <span className={`pill ${r.decision.recommend_apply ? "apply" : "skip"}`}>
                    {r.decision.recommend_apply ? "apply" : "skip"}
                  </span>
                  {r.decision.confidence && <span className="count mono">confidence: {r.decision.confidence}</span>}
                </div>
                <div className="panel">
                  {r.decision.reasons.length > 0 && (
                    <ul className="rlist">{r.decision.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  )}
                  {r.decision.blockers.length > 0 && (
                    <>
                      <p className="kicker" style={{ margin: "14px 0 8px" }}>Blockers</p>
                      <ul className="rlist bad">{r.decision.blockers.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                </div>
              </div>

              {/* sponsorship */}
              <div className="block">
                <div className="block-head">
                  <h2>Sponsorship</h2>
                  <span className={`pill ${r.sponsorship.hard_blocker ? "skip" : "apply"}`}>{r.sponsorship.verdict}</span>
                  {r.sponsorship.needs_verification && <span className="count mono">needs verification</span>}
                </div>
                <div className="panel">
                  <div className="kv">
                    <span className="k">Source</span><span>{r.sponsorship.source || "—"}</span>
                    <span className="k">Hard blocker</span><span>{r.sponsorship.hard_blocker ? "yes" : "no"}</span>
                  </div>
                  {r.sponsorship.reasons.length > 0 && (
                    <ul className="rlist" style={{ marginTop: 12 }}>{r.sponsorship.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  )}
                </div>
              </div>

              {/* gap analysis */}
              <div className="block">
                <div className="block-head"><h2>Requirement analysis</h2><span className="count">{r.gap.items.length} items</span></div>
                <div className="panel">
                  {GAP_GROUPS.map((g) => {
                    const items = r.gap.items.filter((it) => it.status === g.key);
                    if (items.length === 0) return null;
                    return (
                      <div key={g.key} className="gap-group">
                        <p className={`kicker gk-${g.cls}`}>{g.label} · {items.length}</p>
                        {items.map((it, i) => (
                          <div className={`gap-item ${g.cls}`} key={i}>
                            <div className="gi-req">{it.requirement}</div>
                            {it.evidence && <div className="gi-ev">{it.evidence}</div>}
                            {it.substitution && <div className="gi-sub mono">↳ {it.substitution}</div>}
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* keywords */}
              <div className="block">
                <div className="block-head"><h2>Target keywords</h2><span className="count">{r.keyword_set.keywords.length}</span></div>
                <div className="panel">
                  <div className="kw-wrap">
                    {[...r.keyword_set.keywords].sort((a, b) => b.weight - a.weight).map((k, i) => (
                      <span key={i} className={`kw ${k.kind}`} title={`${k.kind} · weight ${k.weight.toFixed(2)}`}>{k.term}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* job description (left, below the analysis) */}
              <div className="block">
                <div className="block-head"><h2>Job description</h2></div>
                <div className="panel">
                  {r.job.required_quals.length > 0 && (
                    <>
                      <p className="kicker">Required</p>
                      <ul className="rlist">{r.job.required_quals.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {r.job.preferred_quals.length > 0 && (
                    <>
                      <p className="kicker" style={{ marginTop: 14 }}>Preferred</p>
                      <ul className="rlist">{r.job.preferred_quals.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {r.job.responsibilities.length > 0 && (
                    <>
                      <p className="kicker" style={{ marginTop: 14 }}>Responsibilities</p>
                      <ul className="rlist">{r.job.responsibilities.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* -------- right: documents (résumé / cover letter), generated on demand -------- */}
            <aside className="report-side">
              <div className="block-head"><h2>Documents</h2></div>
              <div className="panel">
                {r.resume || r.cover_letter ? (
                  <div className="chips">
                    {r.resume != null && <a className="btn btn-sm" href={artifactUrl(runId, "resume.pdf")} target="_blank" rel="noreferrer">résumé PDF ↗</a>}
                    {r.resume != null && <a className="btn btn-sm" href={artifactUrl(runId, "resume.docx")} target="_blank" rel="noreferrer">résumé DOCX ↗</a>}
                    {r.cover_letter != null && <a className="btn btn-sm" href={artifactUrl(runId, "cover_letter.txt")} target="_blank" rel="noreferrer">cover letter ↗</a>}
                  </div>
                ) : (
                  <div className="doc-empty">
                    <div className="doc-empty-art" aria-hidden>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" width="30" height="30">
                        <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                        <path d="M14 3v6h6M8 13h8M8 17h5" />
                      </svg>
                    </div>
                    <p className="muted" style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 4px" }}>
                      No tailored résumé or cover letter yet. Tracking runs a <b>match-only</b> analysis (fit / gap /
                      sponsorship / keywords) — the tailored documents are generated <b>on demand</b>, not
                      automatically, so you only spend the run when you actually want to apply.
                    </p>
                    {gen ? (
                      <button className="btn btn-sm" disabled>
                        <span className="matching mono">generating… {gen.stage}</span>
                      </button>
                    ) : genDone ? (
                      <a className="btn btn-sm btn-primary" href={`/report/${encodeURIComponent(genDone)}`}>view generated documents ↗</a>
                    ) : (
                      <button className="btn btn-sm btn-primary" onClick={generate}>Generate résumé &amp; cover letter</button>
                    )}
                  </div>
                )}
              </div>
            </aside>
          </div>
        )}
      </div>
    </>
  );
}
