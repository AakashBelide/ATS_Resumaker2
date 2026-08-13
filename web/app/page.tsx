"use client";
// Landing page (public `/`, RB.2). Supabase-inspired, in the app's dark-navy + electric/cyan theme.
// Sections: nav, hero, demo slot, feature cards (with inner mocks), a mini app-shell preview whose
// left nav swaps the right panel like the real platform, an animated how-it-works flow, an
// open/self-host band, and a final CTA. No AI-tell punctuation in the copy.
import { AnimatePresence, motion, type Variants } from "framer-motion";
import Link from "next/link";
import { type ReactNode, useState } from "react";

const REPO = "https://github.com/AakashBelide/ATS_Resumaker2";

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 20 },
  show: (i: number = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.5, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] } }),
};
function Reveal({ children, i = 0, className }: { children: ReactNode; i?: number; className?: string }) {
  return (
    <motion.div className={className} variants={fadeUp} custom={i}
      initial="hidden" whileInView="show" viewport={{ once: true, margin: "-70px" }}>
      {children}
    </motion.div>
  );
}
const I = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round" width="22" height="22">{d}</svg>
);
const icons = {
  radar: I(<><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>),
  target: I(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="0.6" fill="currentColor" /></>),
  shield: I(<><path d="M12 3l7 3v6c0 4-3 6.5-7 9-4-2.5-7-5-7-9V6l7-3z" /><path d="M9 12l2 2 4-4" /></>),
  puzzle: I(<path d="M10 4a2 2 0 1 1 4 0v2h3a1 1 0 0 1 1 1v3h-2a2 2 0 1 0 0 4h2v3a1 1 0 0 1-1 1h-3v-2a2 2 0 1 0-4 0v2H7a1 1 0 0 1-1-1v-3H4a2 2 0 1 1 0-4h2V7a1 1 0 0 1 1-1h3V4z" />),
  globe: I(<><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>),
  lock: I(<><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>),
  columns: I(<><rect x="3" y="4" width="7" height="16" rx="1" /><rect x="14" y="4" width="7" height="10" rx="1" /></>),
  link: I(<><path d="M9 15l6-6M10 5l1-1a4 4 0 0 1 6 6l-1 1M14 19l-1 1a4 4 0 0 1-6-6l1-1" /></>),
  user: I(<><circle cx="12" cy="8" r="4" /><path d="M4.5 21c0-4 3.6-6 7.5-6s7.5 2 7.5 6" /></>),
  wand: I(<><path d="M15 4V2M15 10V8M11 6H9M19 6h-2" /><path d="M4 20l10-10 2 2L6 22z" /></>),
  check: I(<path d="M20 6L9 17l-5-5" />),
  spark: I(<path d="M12 3l1.7 5.1L19 10l-5.3 1.9L12 17l-1.7-5.1L5 10l5.3-1.9L12 3z" />),
  github: I(<path d="M9 19c-4 1.5-4-2-5-2.5M15 21v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.9 2.1 5.9 2.4 5.9 2.4a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.5 8.8c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />),
};

// ---- inner "mock" visuals for the feature cards ----------------------------
const MockDiscovery = () => (
  <div className="lp-mock">
    {[72, 60, 66].map((w, i) => (
      <div className="lp-mock-row" key={i}>
        <span className="lp-mock-dot" /><span className="lp-mock-bar" style={{ width: `${w}%` }} />
        <span className="lp-mock-pill">track</span>
      </div>
    ))}
  </div>
);
const MockMatch = () => (
  <div className="lp-mock">
    {[["skills", 64], ["experience", 78], ["domain", 88]].map(([k, v]) => (
      <div className="lp-meter" key={k as string}>
        <span className="lp-meter-l">{k}</span>
        <span className="lp-meter-t"><span className="lp-meter-f" style={{ width: `${v}%` }} /></span>
      </div>
    ))}
    <div className="lp-mock-score">69<small>/100</small> <span className="lp-mock-ok">apply</span></div>
  </div>
);
const MockGate = () => (
  <div className="lp-mock">
    <div className="lp-gate ok">$6M fraud prevented <span>traced to profile</span></div>
    <div className="lp-gate ok">3 yrs experience <span>verified</span></div>
    <div className="lp-gate bad">5+ yrs experience <span>blocked</span></div>
  </div>
);

const PRIMARY = [
  { icon: icons.radar, t: "Deterministic Discovery", d: "A filterable, LLM-free feed of fresh postings from companies you onboard, with no misleading resume-fit ranking.", mock: <MockDiscovery /> },
  { icon: icons.target, t: "Match, then tailor", d: "One click runs fit, gap, sponsorship, and keywords. Generate a grounded resume and cover letter only when you choose to.", mock: <MockMatch /> },
  { icon: icons.shield, t: "Anti-fabrication gate", d: "Every metric, employer, and title must trace to your profile. A mechanical gate blocks anything you cannot defend.", mock: <MockGate /> },
];
const SECONDARY = [
  { icon: icons.spark, t: "Agentic onboarding", d: "Give a company name and Claude resolves its ATS board automatically. $0 beyond your Claude subscription, or bring your own API key." },
  { icon: icons.puzzle, t: "One-click capture", d: "A browser extension grabs any posting (text plus a full-page screenshot) into your tracker." },
  { icon: icons.globe, t: "Sponsorship-aware", d: "USCIS H-1B history and the posting's own stance drive the apply or skip call." },
  { icon: icons.lock, t: "Self-hosted and free", d: "Runs on free tiers, or one small box. Your data stays yours." },
];

// ---- mini app-shell preview (mirrors the real platform after login) --------
const PanelDiscovery = () => (
  <div className="lp-panel">
    <div className="lp-panel-filters">
      <span className="lp-fpill on">AI Engineer</span>
      <span className="lp-fpill">junior</span>
      <span className="lp-fpill">last 1 day</span>
      <span className="lp-fpill ghost">+ filter</span>
    </div>
    {[["Baselayer", 70], ["Ramp", 62], ["Databricks", 66]].map(([co, w]) => (
      <div className="lp-jobrow" key={co as string}>
        <span className="lp-jobrow-logo" />
        <div className="lp-jobrow-txt">
          <span className="lp-jobrow-t">{co} <i>AI Engineer</i></span>
          <span className="lp-line" style={{ width: `${w}%` }} />
        </div>
        <span className="lp-app-pill">+ Track</span>
      </div>
    ))}
  </div>
);
const PanelTracker = () => (
  <div className="lp-panel">
    <div className="lp-trow lp-thead"><span>Company</span><span>Role</span><span className="c">Fit</span><span>Stage</span></div>
    {[["Baselayer", "Identity Graph", 46, "interested"], ["Morgan Stanley", "AI Engineer", 69, "applied"], ["Ramp", "ML Engineer", 58, "interview"]].map((r) => (
      <div className="lp-trow" key={r[0] as string}>
        <span className="lp-tco"><span className="lp-jobrow-logo sm" />{r[0]}</span>
        <span className="dim">{r[1]}</span>
        <span className="c"><b className={`lp-fit ${(r[2] as number) >= 65 ? "hi" : "mid"}`}>{r[2]}</b></span>
        <span className="lp-stage">{r[3]}</span>
      </div>
    ))}
  </div>
);
const PanelOnboard = () => (
  <div className="lp-panel">
    <div className="lp-onb-form">
      <span className="lp-onb-input">Company name</span>
      <span className="lp-app-pill solid">Onboard</span>
    </div>
    <div className="lp-onb-result">
      <div className="lp-onb-line ok">{icons.check}<span>Greenhouse board resolved for Databricks</span></div>
      <div className="lp-onb-agent">{icons.spark}<span>Agent resolved it via Claude CLI</span><em>$0 extra</em></div>
    </div>
  </div>
);
const PanelProfile = () => (
  <div className="lp-panel">
    <div className="lp-prof-stats"><div><b>3</b><span>yrs</span></div><div><b>7</b><span>employers</span></div><div><b>70</b><span>skills</span></div></div>
    <div className="lp-prof-chips">
      {["Python", "FastAPI", "RAG", "LangGraph", "GCP", "Airflow", "Snowflake", "Prompt Eng"].map((s) => <span key={s}>{s}</span>)}
    </div>
  </div>
);
const APP = [
  { key: "discovery", label: "Discovery", icon: icons.radar, panel: <PanelDiscovery /> },
  { key: "tracker", label: "Tracker", icon: icons.columns, panel: <PanelTracker /> },
  { key: "onboard", label: "Onboarding", icon: icons.link, panel: <PanelOnboard /> },
  { key: "profile", label: "Profile", icon: icons.user, panel: <PanelProfile /> },
];

// ---- how-it-works flow ------------------------------------------------------
const FLOW = [
  { icon: icons.spark, t: "Onboard", d: "Name to ATS board, agentically" },
  { icon: icons.radar, t: "Ingest", d: "Poll boards, dedupe new roles" },
  { icon: icons.columns, t: "Track", d: "Fit, gap, sponsorship" },
  { icon: icons.wand, t: "Generate", d: "Resume and cover, grounded" },
  { icon: icons.check, t: "Apply", d: "You decide, human in loop" },
];

export default function LandingPage() {
  const [sec, setSec] = useState(0);
  return (
    <div className="lp">
      <div className="lp-orb lp-orb-a" aria-hidden />
      <div className="lp-orb lp-orb-b" aria-hidden />
      <div className="lp-grid" aria-hidden />

      {/* nav */}
      <header className="lp-nav">
        <div className="lp-brand">
          <span className="rail-hex" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" />
              <path d="M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z" fill="currentColor" opacity="0.35" stroke="none" />
            </svg>
          </span>
          <b>ATS Resumaker</b>
        </div>
        <nav className="lp-nav-links">
          <a className="lp-navlink" href="#features">Features</a>
          <a className="lp-navlink" href="#how">How it works</a>
          <Link className="lp-navlink" href="/setup">Self-host</Link>
          <a className="lp-navlink lp-navicon" href={REPO} target="_blank" rel="noreferrer" title="View on GitHub">{icons.github}</a>
          <Link className="lp-navlink" href="/login">Login</Link>
          <Link className="btn btn-sm btn-primary" href="/login">Get started</Link>
        </nav>
      </header>

      {/* hero */}
      <section className="lp-hero">
        <div className="lp-hero-l">
          <motion.h1 initial="hidden" animate="show" variants={fadeUp} custom={0} className="lp-h1">
            Land interviews faster.<br /><span className="lp-grad">Without the fabrication.</span>
          </motion.h1>
          <motion.div initial="hidden" animate="show" variants={fadeUp} custom={2} className="lp-cta">
            <Link className="btn btn-primary" href="/login">Get started</Link>
            <Link className="btn" href="/setup">Self-host guide</Link>
          </motion.div>
        </div>
        <motion.p initial="hidden" animate="show" variants={fadeUp} custom={1} className="lp-hero-r">
          Watch the companies you care about, surface new roles, and turn any posting into a
          fact-checked, ATS-optimized resume and cover letter, traced strictly to your real
          experience. It advises and drafts; it never auto-applies.
        </motion.p>
      </section>

      {/* demo video slot */}
      <Reveal className="lp-video-wrap">
        <div className="lp-video" role="img" aria-label="Product demo (coming soon)">
          <div className="lp-video-inner">
            <span className="lp-play" aria-hidden>
              <svg viewBox="0 0 24 24" fill="currentColor" width="26" height="26"><path d="M8 5v14l11-7z" /></svg>
            </span>
            <span className="mono muted">demo walkthrough coming soon</span>
          </div>
        </div>
      </Reveal>

      {/* features */}
      <section className="lp-section" id="features">
        <Reveal><h2 className="lp-h2"><span className="lp-h2-dim">A full application platform,</span> not just a resume bot.</h2></Reveal>
        <div className="lp-cards3">
          {PRIMARY.map((f, i) => (
            <Reveal key={f.t} i={i} className="lp-card">
              <span className="lp-card-ico">{f.icon}</span>
              <div className="lp-card-t">{f.t}</div>
              <div className="lp-card-d">{f.d}</div>
              {f.mock}
            </Reveal>
          ))}
        </div>
        <div className="lp-cards4">
          {SECONDARY.map((f, i) => (
            <Reveal key={f.t} i={i} className="lp-card sm">
              <span className="lp-card-ico">{f.icon}</span>
              <div className="lp-card-t">{f.t}</div>
              <div className="lp-card-d">{f.d}</div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* mini app-shell preview */}
      <section className="lp-section">
        <Reveal><h2 className="lp-h2"><span className="lp-h2-dim">See it in action,</span> the whole workflow in one place.</h2></Reveal>
        <Reveal i={1}>
          <div className="lp-app">
            <div className="lp-app-bar"><span /><span /><span /><em className="mono">ats-resumaker</em></div>
            <div className="lp-app-body">
              <nav className="lp-app-nav">
                {APP.map((s, i) => (
                  <button key={s.key} className={`lp-app-navitem ${sec === i ? "on" : ""}`} onClick={() => setSec(i)}>
                    <span className="ico">{s.icon}</span><span>{s.label}</span>
                  </button>
                ))}
              </nav>
              <div className="lp-app-main">
                <AnimatePresence mode="wait">
                  <motion.div key={sec} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>
                    <div className="lp-app-title mono">{APP[sec].label}</div>
                    {APP[sec].panel}
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* how it works: animated flow */}
      <section className="lp-section" id="how">
        <Reveal><p className="lp-kicker mono">How it works</p></Reveal>
        <Reveal i={1}><h2 className="lp-h2">From a company name to a defensible application.</h2></Reveal>
        <div className="lp-flow">
          {FLOW.map((s, i) => (
            <div className="lp-flow-cell" key={s.t}>
              <Reveal i={i} className="lp-flow-box">
                <span className="lp-flow-ico">{s.icon}</span>
                <div className="lp-flow-t">{s.t}</div>
                <div className="lp-flow-d">{s.d}</div>
              </Reveal>
              {i < FLOW.length - 1 && (
                <motion.span className="lp-flow-arrow" aria-hidden
                  initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }}
                  transition={{ delay: i * 0.05 + 0.2 }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                </motion.span>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* open-source / self-host band */}
      <section className="lp-section">
        <div className="lp-os">
          <Reveal className="lp-os-l">
            <p className="lp-kicker mono">Open and self-hosted</p>
            <h2 className="lp-h2">Own the whole stack. Free.</h2>
            <p className="lp-sub" style={{ margin: "10px 0 18px" }}>
              Deploy your own instance on Cloud Run, Turso, and Vercel within their free tiers, or run
              it locally with Docker. The LLM runs on your Claude subscription at no extra cost, or your
              own API key. Read it, self-host it. You are never locked in.
            </p>
            <div className="lp-cta">
              <a className="btn btn-primary" href={REPO} target="_blank" rel="noreferrer">View on GitHub</a>
              <Link className="btn" href="/setup">Self-host guide</Link>
            </div>
          </Reveal>
          <Reveal i={1} className="lp-os-r">
            <div className="lp-stat"><b>$0</b><span>free-tier hostable</span></div>
            <div className="lp-stat"><b>100%</b><span>grounded to your profile</span></div>
            <div className="lp-stat"><b>1-click</b><span>capture and track</span></div>
            <div className="lp-stat"><b>0</b><span>auto-applies (human in loop)</span></div>
          </Reveal>
        </div>
      </section>

      {/* final CTA */}
      <Reveal className="lp-cta-band">
        <h2 className="lp-h2">Land interviews faster, <span className="lp-grad">without the fabrication.</span></h2>
        <div className="lp-cta" style={{ justifyContent: "center", marginTop: 18 }}>
          <Link className="btn btn-primary" href="/login">Get started</Link>
          <Link className="btn" href="/setup">Self-host guide</Link>
        </div>
      </Reveal>

      <footer className="lp-foot">
        <div className="lp-brand">
          <span className="rail-hex" aria-hidden style={{ width: 20, height: 20 }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" /></svg>
          </span>
          <b>ATS Resumaker</b>
        </div>
        <div className="lp-foot-links">
          <a href={REPO} target="_blank" rel="noreferrer">GitHub</a>
          <Link href="/setup">Self-host</Link>
          <Link href="/login">Login</Link>
        </div>
      </footer>
    </div>
  );
}
