"use client";
// First-time deterministic profile seed (no LLM): download the schema template, fill it in, paste it
// back, and load it straight into the canonical profile. Lossless - unlike the resume parser it keeps
// hand-curated structure (equivalence_map, target_archetypes). First-time gated: overwriting an
// existing profile requires an explicit confirm.
import Link from "next/link";
import { useState } from "react";

import { profileTemplate, seedProfile, type ProfileDocument } from "@/lib/api";

export default function ProfileSeed() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [needForce, setNeedForce] = useState(false);
  const [done, setDone] = useState<Record<string, number> | null>(null);

  async function downloadTemplate() {
    setErr("");
    try {
      const { template } = await profileTemplate();
      const blob = new Blob([JSON.stringify(template, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "profile.template.json"; a.click();
      URL.revokeObjectURL(url);
      if (!text.trim()) setText(JSON.stringify(template, null, 2));   // also seed the editor to fill inline
    } catch (e) { setErr(String(e)); }
  }

  async function seed(force: boolean) {
    setErr(""); setNeedForce(false);
    let doc: ProfileDocument;
    try { doc = JSON.parse(text); }
    catch { setErr("That isn't valid JSON. Paste the filled-in template."); return; }
    setBusy(true);
    try {
      const res = await seedProfile(doc, force);
      setDone(res.summary);
    } catch (e) {
      if (String(e).includes("EXISTS")) { setNeedForce(true); setErr("A profile already exists."); }
      else setErr(String(e));
    } finally { setBusy(false); }
  }

  if (done) {
    return (
      <div className="agent">
        <div className="agent-head"><b>Profile seeded</b><span className="mono muted">deterministic</span></div>
        <div className="panel">
          <p style={{ marginBottom: 14 }}>Loaded {done.experience} role(s), {done.projects} project(s), {done.skills} skill(s) into your profile.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link className="btn btn-sm btn-primary" href="/profile-agent">Enrich in Enhance chat →</Link>
            <Link className="btn btn-sm" href="/profile#preferences">Set job preferences →</Link>
            <Link className="btn btn-sm" href="/profile">View profile</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="agent">
      <div className="agent-head"><b>First-time setup</b><span className="mono muted">deterministic · no AI</span></div>
      <div className="panel">
        <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
          Fill the template in your resume&apos;s exact structure and load it straight in - lossless, and it
          keeps hand-curated fields (equivalence map, target roles) the AI parser can&apos;t infer.
        </p>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button className="btn btn-sm" onClick={downloadTemplate} disabled={busy}>Download template</button>
        </div>
        <textarea className="agent-paste" rows={12} value={text}
                  placeholder="Paste your filled-in profile.template.json here…"
                  onChange={(e) => setText(e.target.value)} />
        {err && <p className="error">{err}</p>}
        {needForce ? (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="muted" style={{ fontSize: 13 }}>Overwrite it?</span>
            <button className="btn btn-sm btn-primary" onClick={() => seed(true)} disabled={busy}>Overwrite</button>
            <button className="btn btn-sm" onClick={() => setNeedForce(false)} disabled={busy}>Cancel</button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={() => seed(false)} disabled={busy || !text.trim()}>
            {busy ? "seeding…" : "Seed profile"}
          </button>
        )}
      </div>
    </div>
  );
}
