"use client";
// Profile agent page: three flows in one place. Onboard (intake), Enhance (free chat), and Gap
// clarification (opened from the report page's "talk to the agent" nudge with ?mode=gapchat&run=).
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import AgentChat from "@/components/AgentChat";
import ProfileSeed from "@/components/ProfileSeed";

type Tab = "enhance" | "intake";
type OnboardMode = "seed" | "parse";

function ProfileAgentInner() {
  const params = useSearchParams();
  const gapRun = params.get("mode") === "gapchat" ? params.get("run") : null;
  const [tab, setTab] = useState<Tab>("enhance");
  const [onboardMode, setOnboardMode] = useState<OnboardMode>("seed");

  if (gapRun) {
    return (
      <>
        <header className="topbar"><div><div className="kicker">Profile agent</div><h1>Clarify gaps</h1></div></header>
        <div className="page">
          <p className="muted" style={{ maxWidth: 640, marginBottom: 16 }}>
            Confirm which of the job&apos;s requirements you&apos;ve actually worked on. I only add what you
            confirm; then <b>/generate</b> re-computes your fit and produces the tailored resume.
          </p>
          <AgentChat mode="gapchat" reportRunId={gapRun} title="Gap clarification" />
        </div>
      </>
    );
  }

  return (
    <>
      <header className="topbar"><div><div className="kicker">Profile agent</div><h1>Build &amp; enrich your profile</h1></div></header>
      <div className="page">
        <div className="seg" style={{ marginBottom: 18 }}>
          <button className={`seg-btn ${tab === "enhance" ? "on" : ""}`} onClick={() => setTab("enhance")}>Enhance (chat)</button>
          <button className={`seg-btn ${tab === "intake" ? "on" : ""}`} onClick={() => setTab("intake")}>Onboard (paste resume)</button>
        </div>
        <p className="muted" style={{ maxWidth: 640, marginBottom: 16 }}>
          {tab === "enhance"
            ? "Tell me about projects, metrics, or skills that aren't captured yet — a Snowflake table you built, a latency you cut, who used it. I only record what you confirm, and everything is reversible with /undo."
            : "Onboard a profile two ways: fill a structured template for an exact, lossless load, or paste your resume and let the agent parse it (then flag thin spots)."}
        </p>
        {tab === "enhance" ? (
          <AgentChat mode="enhance" title="Enhancement chat" />
        ) : (
          <>
            <div className="seg" style={{ marginBottom: 16 }}>
              <button className={`seg-btn ${onboardMode === "seed" ? "on" : ""}`} onClick={() => setOnboardMode("seed")}>First time · template</button>
              <button className={`seg-btn ${onboardMode === "parse" ? "on" : ""}`} onClick={() => setOnboardMode("parse")}>Paste resume · AI parse</button>
            </div>
            {onboardMode === "seed" ? <ProfileSeed /> : <AgentChat mode="intake" title="Onboarding intake" />}
          </>
        )}
      </div>
    </>
  );
}

export default function ProfileAgentPage() {
  return <Suspense fallback={<div className="page">loading…</div>}><ProfileAgentInner /></Suspense>;
}
