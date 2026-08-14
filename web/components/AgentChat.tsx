"use client";
// Reusable chat panel for the profile agent (enhance / intake / gapchat). Drives the POC API:
// start -> say -> poll. Renders the conversation, pending proposals (with Apply/Skip), the event
// timeline, and slash-command buttons. For a gapchat /generate it polls until the run finishes so
// the score delta lands.
import { useCallback, useEffect, useRef, useState } from "react";

import { agentSay, getAgent, startAgent, stopAgent, type AgentState } from "@/lib/api";

type Props = {
  mode: "enhance" | "intake" | "gapchat";
  reportRunId?: string;          // gapchat
  seedRunId?: string;            // resume an existing run
  title?: string;
};

export default function AgentChat({ mode, reportRunId, seedRunId, title }: Props) {
  const [st, setSt] = useState<AgentState | null>(null);
  const [input, setInput] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const boot = useCallback(async () => {
    setErr("");
    try {
      if (seedRunId) setSt(await getAgent(seedRunId));
      else if (mode !== "intake") setSt(await startAgent(mode, { report_run_id: reportRunId }));
    } catch (e) { setErr(String(e)); }
  }, [mode, reportRunId, seedRunId]);

  useEffect(() => { boot(); }, [boot]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: 1e9 }); }, [st?.history?.length]);

  // poll while a gapchat generation is running
  useEffect(() => {
    const running = st?.state === "running";
    if (running && !pollRef.current && st) {
      pollRef.current = setInterval(async () => {
        try {
          const next = await getAgent(st.run_id);
          setSt(next);
          if (next.state !== "running" && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        } catch { /* keep polling */ }
      }, 2500);
    }
    return () => { if (pollRef.current && st?.state !== "running") { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [st?.state, st?.run_id]);

  async function send(msg: string) {
    if (!st || !msg.trim() || busy) return;
    setBusy(true); setErr("");
    try { setSt(await agentSay(st.run_id, msg)); setInput(""); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  async function startIntake() {
    if (!resumeText.trim() || busy) return;
    setBusy(true); setErr("");
    try { setSt(await startAgent("intake", { resume_text: resumeText })); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  const done = st && ["done", "stopped", "error"].includes(st.state);

  // intake: show the paste box until a run exists
  if (mode === "intake" && !st) {
    return (
      <div className="agent">
        <div className="agent-head"><b>{title ?? "Onboarding intake"}</b>
          <span className="mono muted">paste your resume text</span></div>
        <textarea className="agent-paste" rows={12} value={resumeText} placeholder="Paste your resume (or LinkedIn export) text here…"
                  onChange={(e) => setResumeText(e.target.value)} />
        {err && <p className="error">{err}</p>}
        <button className="btn btn-primary" onClick={startIntake} disabled={busy || !resumeText.trim()}>
          {busy ? "parsing…" : "Parse into profile"}</button>
      </div>
    );
  }

  return (
    <div className="agent">
      <div className="agent-head">
        <b>{title ?? "Profile agent"}</b>
        <span className="mono muted">{st ? `${st.mode} · ${st.state}` : "starting…"}</span>
        {st && !done && <button className="btn btn-sm" onClick={async () => setSt(await stopAgent(st.run_id))}>Stop</button>}
      </div>

      {/* seeded gap talking-points */}
      {mode === "gapchat" && st?.meta?.gap_lines != null && (
        <div className="agent-seed">
          <span className="kicker">Gaps to clarify</span>
          <div className="mono">{(st.meta.gap_lines as string[]).join("  ") || "none"}</div>
          {(st.meta.unlisted_lines as string[])?.length > 0 && (
            <><span className="kicker" style={{ marginTop: 6 }}>You may already have</span>
              <div className="mono">{(st.meta.unlisted_lines as string[]).join("  ")}</div></>
          )}
        </div>
      )}

      <div className="agent-log" ref={scrollRef}>
        {(st?.history ?? []).map((m, i) => (
          <div key={i} className={`agent-msg ${m.role}`}><span>{m.text}</span></div>
        ))}
        {st && st.history.length === 0 && (
          <div className="agent-msg agent">
            <span>{mode === "gapchat"
              ? "Tell me about any of these the job wants — have you actually done them? I'll only add what you confirm."
              : "Tell me about a project, skill, or metric that isn't captured yet. I only record what you confirm."}</span>
          </div>
        )}
      </div>

      {/* pending proposals */}
      {st && st.pending.length > 0 && (
        <div className="agent-pending">
          <span className="kicker">Proposed changes</span>
          {st.pending.map((p, i) => (
            <div key={i} className="agent-prop">
              <span>{p.preview || p.kind}</span>
              <span className="mono muted">“{p.source_quote.slice(0, 48)}”</span>
            </div>
          ))}
          <div className="agent-prop-actions">
            <button className="btn btn-sm btn-primary" onClick={() => send("yes")} disabled={busy}>Apply</button>
            <button className="btn btn-sm" onClick={() => send("/skip")} disabled={busy}>Skip</button>
          </div>
        </div>
      )}

      {/* input + slash commands */}
      {!done && st && (
        <div className="agent-input">
          <input value={input} placeholder="Type a message, or /help" disabled={busy}
                 onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") send(input); }} />
          <button className="btn btn-primary" onClick={() => send(input)} disabled={busy || !input.trim()}>Send</button>
        </div>
      )}
      {!done && st && (
        <div className="agent-slash">
          {mode === "gapchat" && <button className="btn btn-sm btn-primary" onClick={() => send("/generate")} disabled={busy}>/generate</button>}
          <button className="btn btn-sm" onClick={() => send("/done")} disabled={busy}>/done</button>
          <button className="btn btn-sm" onClick={() => send("/undo")} disabled={busy}>/undo</button>
          <button className="btn btn-sm" onClick={() => send("/help")} disabled={busy}>/help</button>
        </div>
      )}

      {busy && <p className="mono muted" style={{ fontSize: 12 }}>working…</p>}
      {err && <p className="error">{err}</p>}
      {done && <p className="mono muted">Run {st?.state}. {st?.meta?.new_fit != null && `Fit is now ${Math.round(Number(st.meta.new_fit))}.`}</p>}
    </div>
  );
}
