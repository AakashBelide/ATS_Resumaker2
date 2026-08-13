"use client";
// Match-report detail: renders outputs/<run_id>/report.json as a readable analysis instead
// of raw JSON. Its own route (linked from the Tracker). Match-only runs have no resume/ATS
// sections, so those are shown only when present.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Spinner from "@/components/Spinner";

import CompanyLogo from "@/components/CompanyLogo";
import { artifactDownloadUrl, artifactUrl, fetchArtifactText, getProgress, getReport, getReportOrNull, getRun, getTrackerByRun, startRun, uploadResume, type Report, type TrackerEntry } from "@/lib/api";

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
  const [matchTimedOut, setMatchTimedOut] = useState(false);          // match poll hit its cap, still 404
  const [reloadNonce, setReloadNonce] = useState(0);                  // bumped by "refresh" to re-poll
  const [gen, setGen] = useState<{ stage: string } | null>(null);   // in-progress generation
  const genPoll = useRef<ReturnType<typeof setInterval> | null>(null); // active generation-poll interval
  const [tracked, setTracked] = useState<TrackerEntry | null>(null); // authoritative ATS title/company
  const [docTab, setDocTab] = useState<"resume" | "cover">("resume"); // which document is previewed
  const [coverText, setCoverText] = useState<string | null>(null);    // cover letter body, fetched inline
  const [copied, setCopied] = useState(false);                        // cover-letter copy feedback
  const [uploading, setUploading] = useState(false);                  // own-PDF upload in flight
  const fileRef = useRef<HTMLInputElement>(null);                     // hidden file picker for PDF upload
  // Extension capture screenshot: a full-page PNG or (for tall pages) JPEG. Try each in turn and
  // hide the block if neither exists (most runs have no capture). `shotIdx` walks the candidates.
  const shotCandidates = ["screenshot.png", "screenshot.jpg"];
  const [shotIdx, setShotIdx] = useState(0);
  const shotUrl = shotIdx < shotCandidates.length ? artifactUrl(runId, shotCandidates[shotIdx]) : "";

  async function copyCover() {
    if (!coverText) return;
    try { await navigator.clipboard.writeText(coverText); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  }

  // Upload the owner's own resume PDF for this run (instead of generating one). Reads the file as a
  // base64 data URL, POSTs it, then re-polls the report so the uploaded PDF renders in the resume tab.
  function pickPdf() { fileRef.current?.click(); }
  async function onPdfChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";                              // allow re-picking the same file later
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) { setError("please choose a PDF file"); return; }
    if (f.size > 15 * 1024 * 1024) { setError("PDF too large (max 15MB)"); return; }
    setUploading(true); setError("");
    try {
      const dataUrl: string = await new Promise((res, rej) => {
        const reader = new FileReader();
        reader.onload = () => res(String(reader.result));
        reader.onerror = () => rej(new Error("could not read the file"));
        reader.readAsDataURL(f);
      });
      await uploadResume(runId, dataUrl, f.name);
      const rep = await getReport(runId).catch(() => null);   // reflect the uploaded PDF immediately
      if (rep) setR(rep); else retry();
    } catch (err) { setError(String(err)); }
    finally { setUploading(false); }
  }

  // Shared generation-progress loop: poll the run until it ends, then reload the report so the
  // freshly published resume/cover letter render. Used by BOTH the Generate button (which starts a
  // run first) and mount-resume (which reattaches to a generation already in flight after the user
  // navigated away and came back). Returns the interval id so callers can stash it for cleanup.
  const pollUntilDone = useCallback((run_id: string) => {
    // Poll progress (no SSE): status.json gives the live stage; `done` ends the loop, then one
    // getRun tells us success vs error. status.json may not exist for the first tick.
    const poll = setInterval(async () => {
      try {
        const p = await getProgress(run_id);
        if (p.current) setGen({ stage: p.current });
        if (p.done) {
          clearInterval(poll);
          const rec = await getRun(run_id).catch(() => null);
          if (rec && rec.status === "error") { setGen(null); setError("generation failed - see the run log"); return; }
          // The worker marks the run done a beat before it finishes publishing to GCS, so poll the
          // report until the resume actually appears, then reveal the documents.
          setGen({ stage: "finishing" });
          for (let i = 0; i < 8; i++) {
            const rep = await getReport(runId).catch(() => null);
            if (rep && (rep.resume || rep.cover_letter)) { setR(rep); break; }
            await new Promise((res) => setTimeout(res, 1500));
          }
          setGen(null);
        }
      } catch { /* status.json not written yet - keep polling */ }
    }, 2000);
    genPoll.current = poll;
    return poll;
  }, [runId]);

  // Mount / retry: the report page can be opened while the MATCH is still running, so report.json
  // 404s at first. Instead of dead-ending in an error box, poll getReportOrNull every ~2.5s and show
  // a "matching…" state until it publishes. Once it loads, if the match is done but no documents
  // exist yet AND the run is currently "running", a generation is in flight (started before we
  // navigated away) - reattach to it (Fix 2) rather than showing the Generate button again. Only a
  // genuine non-404 failure surfaces the hard error box; a persistent 404 (cap ~40 tries) softens to
  // a "still matching, check back" message instead of an error.
  useEffect(() => {
    let cancelled = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setError(""); setMatchTimedOut(false);

    const attempt = async () => {
      try {
        const rep = await getReportOrNull(runId);
        if (cancelled) return;
        if (rep) {
          setR(rep);
          if (!rep.resume && !rep.cover_letter) {
            // Fix 2: resume an already-running generation on mount (do NOT start a new one).
            const rec = await getRun(runId).catch(() => null);
            if (!cancelled && rec && rec.status === "running") {
              setGen({ stage: "resuming" });
              pollUntilDone(runId);
            }
          }
          return;                                     // report ready -> stop the matching poll
        }
        tries += 1;                                   // still 404 -> match not published yet
        if (tries >= 40) { setMatchTimedOut(true); return; }   // soft cap; stop hammering
        timer = setTimeout(attempt, 2500);
      } catch (e) {
        if (!cancelled) setError(String(e));          // genuine/persistent failure -> hard error box
      }
    };
    attempt();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      if (genPoll.current) { clearInterval(genPoll.current); genPoll.current = null; }
    };
  }, [runId, reloadNonce, pollUntilDone]);
  const retry = useCallback(() => { setR(null); setError(""); setMatchTimedOut(false); setReloadNonce((n) => n + 1); }, []);
  // The tracker keeps the real ATS posting title/company (report.json holds the JD-extracted one,
  // which can differ) - prefer it in the header so the report matches the Tracker card.
  useEffect(() => { getTrackerByRun(runId).then(setTracked).catch(() => {}); }, [runId]);

  // Pull the cover-letter text once it exists, to render it inline (not just a download link).
  useEffect(() => {
    if (r?.cover_letter != null) fetchArtifactText(runId, "cover_letter.txt").then(setCoverText).catch(() => {});
    else setCoverText(null);
  }, [runId, r?.cover_letter]);

  const title = tracked?.title || r?.job.title || "…";
  const company = tracked?.company || r?.job.company || "";
  const uploaded = !!(r?.resume && (r.resume as { uploaded?: boolean }).uploaded);  // owner's own PDF

  async function generate() {
    if (!r) return;
    setGen({ stage: "starting" }); setError("");
    try {
      // Reuse THIS report's run_id so the resume is written into the same folder; on success we
      // just reload the report (it now carries the resume + cover), so a refresh keeps showing it.
      // The button STARTS a run, then hands off to the same poll loop mount-resume uses.
      const { run_id } = await startRun(r.url, runId);
      pollUntilDone(run_id);
    } catch (e) { setError(String(e)); setGen(null); }
  }

  return (
    <>
      <header className="topbar">
        <div>
          <Link className="btn btn-sm" href="/tracker" style={{ marginBottom: 12 }}>‹ back to tracker</Link>
          <div className="kicker">Match report</div>
          <h1 style={{ marginTop: 6 }}>{title}</h1>
        </div>
      </header>

      <div className="page">
        {error && (
          <div className="empty" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
            <span className="error">{error}</span>
            <span className="muted" style={{ fontSize: 12.5 }}>The API may have just restarted. Try again.</span>
            <button className="btn btn-sm btn-primary" onClick={retry}>retry</button>
          </div>
        )}
        {/* match still running: report.json 404s until it publishes. Show a friendly loading state
            (not an error) and let the mount poll fill it in. After the cap, soften to "check back". */}
        {!r && !error && !matchTimedOut && (
          <div className="empty" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
            <Spinner />
            <span className="matching mono">matching… fit fills in shortly</span>
          </div>
        )}
        {!r && !error && matchTimedOut && (
          <div className="empty" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
            <span className="muted">still matching — check back in a moment</span>
            <button className="btn btn-sm btn-primary" onClick={retry}>refresh</button>
          </div>
        )}
        {r && (
          <div className="report-grid">
            {/* -------- left: analysis -------- */}
            <div className="report-main">
              <div className="report-head">
                <CompanyLogo name={company} size={52} />
                <div>
                  <div className="rh-co">{company}</div>
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

            {/* -------- right: documents (resume / cover letter), generated on demand -------- */}
            <aside className="report-side">
              <div className="block-head"><h2>Documents</h2></div>
              <div className="panel">
                {/* one hidden picker shared by every "upload PDF" affordance below */}
                <input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden onChange={onPdfChosen} />
                {r.resume || r.cover_letter ? (
                  <div className="docs">
                    <div className="doc-tabs">
                      {r.resume != null && (
                        <button className={`doc-tab ${docTab === "resume" ? "on" : ""}`} onClick={() => setDocTab("resume")}>resume</button>
                      )}
                      {/* cover letter tab when present; otherwise a muted "unavailable" marker (e.g. an
                          uploaded PDF, which carries no cover letter) so the absence is explicit. */}
                      {r.cover_letter != null ? (
                        <button className={`doc-tab ${docTab === "cover" ? "on" : ""}`} onClick={() => setDocTab("cover")}>cover letter</button>
                      ) : (
                        <span className="doc-na" title="no cover letter for this run">cover letter · unavailable</span>
                      )}
                      <span className="doc-actions">
                        {r.resume != null && docTab === "resume" && (
                          <>
                            {/* direct downloads (attachment, no signed-URL redirect) */}
                            <a className="btn btn-sm" href={artifactDownloadUrl(runId, "resume.pdf")} download>PDF ↓</a>
                            {/* DOCX exists only for a GENERATED resume; an uploaded PDF has none. */}
                            {uploaded
                              ? <span className="doc-na" title="only a PDF was uploaded">DOCX · unavailable</span>
                              : <a className="btn btn-sm" href={artifactDownloadUrl(runId, "resume.docx")} download>DOCX ↓</a>}
                            <button className="btn btn-sm" onClick={pickPdf} disabled={uploading}>{uploading ? "uploading…" : "replace PDF"}</button>
                          </>
                        )}
                        {/* cover letter: copy only - no open/redirect (the body renders inline below) */}
                        {r.cover_letter != null && docTab === "cover" && (
                          <button className="btn btn-sm" onClick={copyCover} disabled={!coverText}>{copied ? "copied ✓" : "copy ⧉"}</button>
                        )}
                      </span>
                    </div>
                    {r.resume != null && docTab === "resume" && (
                      <iframe className="doc-frame" src={artifactUrl(runId, "resume.pdf")} title="resume PDF" />
                    )}
                    {r.cover_letter != null && docTab === "cover" && (
                      <pre className="doc-cover">{coverText ?? "loading…"}</pre>
                    )}
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
                      No tailored resume or cover letter yet. Tracking runs a <b>match-only</b> analysis (fit / gap /
                      sponsorship / keywords) — the tailored documents are generated <b>on demand</b>, not
                      automatically, so you only spend the run when you actually want to apply.
                    </p>
                    <div className="doc-cta">
                      {gen ? (
                        <button className="btn btn-sm" disabled>
                          <span className="matching mono">generating… {gen.stage}</span>
                        </button>
                      ) : (
                        <button className="btn btn-sm btn-primary" onClick={generate}>Generate resume &amp; cover letter</button>
                      )}
                      {/* or attach your own PDF (kept in the bucket for this run) */}
                      <button className="btn btn-sm" onClick={pickPdf} disabled={uploading || !!gen}>
                        {uploading ? "uploading…" : "Upload your own PDF"}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* captured posting (browser-extension screenshot) — lives in the RIGHT column next to
                  the documents, only when one exists. Rendered optimistically; the whole block hides
                  if the image 404s (no run has a screenshot unless it came via capture). */}
              {shotUrl && (
                <div className="block" style={{ marginTop: 22 }}>
                  <div className="block-head"><h2>Captured posting</h2></div>
                  <div className="panel">
                    {/* Scrollable full-page capture (like the reference extension): the image shows at
                        full width and NATURAL height inside a scroll box, so the whole posting is
                        readable in place instead of a cropped thumbnail. */}
                    <div className="shot-scroll">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img className="shot-full" src={shotUrl} alt="captured job posting"
                           onError={() => setShotIdx((i) => i + 1)} />
                    </div>
                    <p className="mono muted" style={{ fontSize: 11.5, marginTop: 10 }}>
                      full-page capture by the browser extension · scroll to read ·{" "}
                      <a href={shotUrl} target="_blank" rel="noreferrer">open full size ↗</a>
                    </p>
                  </div>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
    </>
  );
}
