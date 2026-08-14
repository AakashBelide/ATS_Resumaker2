"use client";
// AI resume parse: upload a PDF/DOCX/TXT (or paste text) -> zero-invention LLM parse -> review the
// extracted profile + thin spots -> apply. Parsing never persists; applying goes through the same
// first-time-gated /seed as the deterministic path, so it can't silently clobber an existing profile.
import Link from "next/link";
import { useState } from "react";

import { parseResume, seedProfile, type ParsedResume } from "@/lib/api";

export default function ProfileIntake() {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<"" | "parsing" | "applying">("");
  const [err, setErr] = useState("");
  const [parsed, setParsed] = useState<ParsedResume | null>(null);
  const [needForce, setNeedForce] = useState(false);
  const [applied, setApplied] = useState<Record<string, number> | null>(null);

  async function doParse() {
    setErr(""); setParsed(null); setApplied(null);
    const input = file ?? text;
    if (typeof input === "string" && !input.trim()) { setErr("Upload a file or paste your resume text."); return; }
    setBusy("parsing");
    try { setParsed(await parseResume(input)); }
    catch (e) { setErr(String(e instanceof Error ? e.message : e)); }
    finally { setBusy(""); }
  }

  async function apply(force: boolean) {
    if (!parsed) return;
    setErr(""); setNeedForce(false); setBusy("applying");
    try { setApplied((await seedProfile(parsed.profile, force)).summary); }
    catch (e) {
      if (String(e).includes("EXISTS")) { setNeedForce(true); setErr("A profile already exists."); }
      else setErr(String(e instanceof Error ? e.message : e));
    } finally { setBusy(""); }
  }

  if (applied) {
    const thin = parsed?.thin_spots ?? [];
    return (
      <div className="agent">
        <div className="agent-head"><b>Profile updated</b><span className="mono muted">from resume</span></div>
        <div className="panel">
          <p style={{ marginBottom: 14 }}>Loaded {applied.experience} role(s), {applied.projects} project(s), {applied.skills} skill(s).</p>
          {thin.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <p className="kicker" style={{ marginBottom: 6 }}>Strengthen these next</p>
              <ul className="doc-bullets">{thin.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link className="btn btn-sm btn-primary" href="/profile-agent">Fill gaps in Enhance chat →</Link>
            <Link className="btn btn-sm" href="/profile#preferences">Set job preferences →</Link>
            <Link className="btn btn-sm" href="/profile">View profile</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="agent">
      <div className="agent-head"><b>Onboarding intake</b><span className="mono muted">AI parse · review before apply</span></div>
      <div className="panel">
        {!parsed ? (
          <>
            <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
              Upload your resume (PDF, DOCX, or TXT) or paste the text. I parse it with zero invention,
              then you review before anything is saved.
            </p>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
              <label className="btn btn-sm" style={{ cursor: "pointer" }}>
                {file ? "Change file" : "Choose file"}
                <input type="file" accept=".pdf,.docx,.txt,.md" style={{ display: "none" }}
                       onChange={(e) => { setFile(e.target.files?.[0] ?? null); setErr(""); }} />
              </label>
              {file && <span className="mono muted" style={{ fontSize: 12 }}>{file.name}</span>}
              {file && <button className="btn btn-sm" onClick={() => setFile(null)}>clear</button>}
            </div>
            {!file && (
              <textarea className="agent-paste" rows={10} value={text} placeholder="…or paste your resume text here"
                        onChange={(e) => setText(e.target.value)} />
            )}
            {err && <p className="error">{err}</p>}
            <button className="btn btn-primary" onClick={doParse} disabled={busy !== "" || (!file && !text.trim())}>
              {busy === "parsing" ? "parsing…" : "Parse resume"}
            </button>
          </>
        ) : (
          <>
            <p className="kicker" style={{ marginBottom: 10 }}>Parsed · review before applying</p>
            <p style={{ marginBottom: 12 }}>
              Found <b>{parsed.summary.experience}</b> role(s), <b>{parsed.summary.projects}</b> project(s),
              <b> {parsed.summary.skills}</b> skill(s).
            </p>
            {parsed.thin_spots.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <p className="kicker" style={{ marginBottom: 6 }}>Thin spots to fill later</p>
                <ul className="doc-bullets">{parsed.thin_spots.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
            )}
            {err && <p className="error">{err}</p>}
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              {needForce ? (
                <>
                  <span className="muted" style={{ fontSize: 13 }}>Overwrite the existing profile?</span>
                  <button className="btn btn-sm btn-primary" onClick={() => apply(true)} disabled={busy !== ""}>Overwrite</button>
                  <button className="btn btn-sm" onClick={() => setNeedForce(false)} disabled={busy !== ""}>Cancel</button>
                </>
              ) : (
                <button className="btn btn-primary" onClick={() => apply(false)} disabled={busy !== ""}>
                  {busy === "applying" ? "applying…" : "Apply to profile"}
                </button>
              )}
              <button className="btn btn-sm" onClick={() => { setParsed(null); setErr(""); }} disabled={busy !== ""}>Start over</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
