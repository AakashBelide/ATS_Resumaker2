"use client";
// Mailer: all email-digest controls in one place — title/level/state filters, send frequency
// (drives Cloud Scheduler), quiet hours, and a max-postings cap ("X of N").
import { useEffect, useState } from "react";

import Select from "@/components/Select";
import Spinner from "@/components/Spinner";
import { getMailerPrefs, previewMailer, saveMailerPrefs, type MailerPreview, type MailerPrefs } from "@/lib/api";

const LEVELS = ["intern", "junior", "mid", "senior", "staff", "manager"];
const FREQ = [
  { value: "off", label: "off (paused)" },
  { value: "hourly", label: "every hour" },
  { value: "every_4h", label: "every 4 hours" },
  { value: "every_12h", label: "every 12 hours" },
  { value: "daily", label: "daily · 8am" },
];

export default function MailerPage() {
  const [p, setP] = useState<MailerPrefs | null>(null);
  const [inc, setInc] = useState("");
  const [exc, setExc] = useState("");
  const [states, setStates] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<"" | "saving" | "saved">("");
  const [preview, setPreview] = useState<MailerPreview | null>(null);

  useEffect(() => {
    getMailerPrefs().then((mp) => {
      setP(mp); setInc(mp.include.join(", ")); setExc(mp.exclude.join(", ")); setStates(mp.states.join(", "));
    }).catch((e) => setError(String(e)));
  }, []);

  const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  // the current (possibly unsaved) filter, as the API expects it
  const currentPrefs = (): MailerPrefs | null => (p
    ? { ...p, include: csv(inc), exclude: csv(exc), states: csv(states).map((s) => s.toUpperCase()) }
    : null);

  // live "X of N": debounce so tuning filters doesn't spam the endpoint
  useEffect(() => {
    const body = currentPrefs();
    if (!body) return;
    const t = setTimeout(() => { previewMailer(body).then(setPreview).catch(() => {}); }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p, inc, exc, states]);

  const patch = (x: Partial<MailerPrefs>) => setP((prev) => (prev ? { ...prev, ...x } : prev));
  const toggleLevel = (l: string) => setP((prev) => (prev
    ? { ...prev, levels: prev.levels.includes(l) ? prev.levels.filter((x) => x !== l) : [...prev.levels, l] }
    : prev));

  async function save() {
    const body = currentPrefs();
    if (!body) return;
    setSaved("saving");
    try {
      const out = await saveMailerPrefs(body);
      setP(out); setInc(out.include.join(", ")); setExc(out.exclude.join(", ")); setStates(out.states.join(", "));
      setSaved("saved"); setTimeout(() => setSaved(""), 2000);
    } catch (e) { setError(String(e)); setSaved(""); }
  }

  return (
    <>
      <header className="topbar">
        <div><div className="kicker">Mailer</div><h1 style={{ marginTop: 6 }}>Email digest</h1></div>
        <div className="topbar-spacer" />
        {p && <span className="mono muted">{p.frequency === "off" ? "paused" : p.frequency.replace("_", " ")}</span>}
      </header>

      <div className="page">
        {error && <p className="error">{error}</p>}
        {!p ? <Spinner /> : (
          <>
            <div className="mailer-preview" aria-live="polite">
              {preview ? (
                <>
                  <div className="mp-nums">
                    <span className="mp-big">{preview.would_send}</span>
                    <span className="mp-of">of</span>
                    <span className="mp-big">{preview.matching}</span>
                    <span className="mp-lead">matching postings would be emailed{preview.cap ? ` · capped at ${preview.cap}/email` : ""}</span>
                  </div>
                  <div className="mp-sub">
                    {preview.matching} of {preview.on_target} on-target postings match your title / level / state filter
                  </div>
                </>
              ) : <span className="mono muted">counting…</span>}
            </div>

            <div className="block">
              <div className="block-head"><h2>What gets emailed</h2><span className="count">on top of the on-target gate</span></div>
              <div className="panel">
                <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  A new posting is emailed only if its <b>title</b> has ANY &ldquo;has&rdquo; word and NONE of the
                  &ldquo;no&rdquo; words, and it matches the selected levels + states. Leave blank for no extra narrowing.
                </p>
                <div className="filters" style={{ marginBottom: 14 }}>
                  <div className="field"><label>title has</label>
                    <input placeholder="ai, ml (any)" value={inc} onChange={(e) => setInc(e.target.value)} /></div>
                  <div className="field"><label>title no</label>
                    <input placeholder="java, manager" value={exc} onChange={(e) => setExc(e.target.value)} /></div>
                  <div className="field"><label>states</label>
                    <input placeholder="MA, NY, CA" value={states} onChange={(e) => setStates(e.target.value)} /></div>
                </div>
                <label className="kicker" style={{ display: "block", marginBottom: 8 }}>seniority levels · none = all</label>
                <div className="chips">
                  {LEVELS.map((l) => (
                    <span key={l} className={`chip${p.levels.includes(l) ? " on" : ""}`}
                          style={{ cursor: "pointer" }} onClick={() => toggleLevel(l)}>{l}</span>
                  ))}
                </div>
              </div>
            </div>

            <div className="block">
              <div className="block-head"><h2>Schedule &amp; volume</h2></div>
              <div className="panel">
                <div className="filters" style={{ marginBottom: 14 }}>
                  <Select label="frequency" value={p.frequency} options={FREQ} onChange={(v) => patch({ frequency: v })} />
                  <div className="field"><label>max per email</label>
                    <input type="number" min={0} placeholder="0 = no cap" value={p.max_postings || ""}
                           onChange={(e) => patch({ max_postings: Number(e.target.value) || 0 })} /></div>
                </div>
                <label className="kicker" style={{ display: "block", marginBottom: 8 }}>quiet hours · no email sent in this window</label>
                <div className="filters">
                  <div className="field"><label>from</label>
                    <input type="time" value={p.quiet_start} onChange={(e) => patch({ quiet_start: e.target.value })} /></div>
                  <div className="field"><label>to</label>
                    <input type="time" value={p.quiet_end} onChange={(e) => patch({ quiet_end: e.target.value })} /></div>
                  <div className="field"><label>timezone</label>
                    <input placeholder="America/New_York" value={p.timezone} onChange={(e) => patch({ timezone: e.target.value })} /></div>
                </div>
                <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>
                  When a run has more than <b>max per email</b> matches, the digest sends that many and reads
                  &ldquo;X of N&rdquo; &mdash; the rest are on Discovery. Frequency sets how often the digest is sent
                  (its own schedule, independent of discovery); &ldquo;off&rdquo; pauses email without affecting ingestion.
                </p>
              </div>
            </div>

            <button className="btn btn-primary" onClick={save} disabled={saved === "saving"}>
              {saved === "saving" ? "saving…" : saved === "saved" ? "saved ✓" : "Save mailer settings"}
            </button>
          </>
        )}
      </div>
    </>
  );
}
