"use client";
// Landing page (public `/`, RB.2 redesign). Supabase-inspired structure, left-aligned hero with a
// gradient second line, feature cards with inner mocks, a tabbed product preview, how-it-works, an
// open-source/self-host band, and a final CTA, all in the app's dark-navy + electric/cyan theme.
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
  github: I(<path d="M9 19c-4 1.5-4-2-5-2.5M15 21v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.9 2.1 5.9 2.4 5.9 2.4a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.5 8.8c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />),
};

// ---- small inner "mock" visuals for the feature cards ----------------------
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
    <div className="lp-gate ok">✓ $6M fraud prevented <span>traced to profile</span></div>
    <div className="lp-gate ok">✓ 3 yrs experience <span>verified</span></div>
    <div className="lp-gate bad">✗ 5+ yrs experience <span>blocked</span></div>
  </div>
);

const PRIMARY = [
  { icon: icons.radar, t: "Deterministic Discovery", d: "A filterable, LLM-free feed of fresh postings from companies you onboard, with no misleading resume-fit ranking.", mock: <MockDiscovery /> },
  { icon: icons.target, t: "Match, then tailor", d: "One click runs fit, gap, sponsorship, and keywords. Generate a grounded resume and cover letter only when you choose to.", mock: <MockMatch /> },
  { icon: icons.shield, t: "Anti-fabrication gate", d: "Every metric, employer, and title must trace to your profile. A mechanical gate blocks anything you cannot defend.", mock: <MockGate /> },
];
const SECONDARY = [
  { icon: icons.puzzle, t: "One-click capture", d: "A browser extension grabs any posting (text + full-page screenshot) into your tracker." },
  { icon: icons.globe, t: "Sponsorship-aware", d: "USCIS H-1B history + the JD's stance drive the apply/no-apply call." },
  { icon: icons.columns, t: "Application tracker", d: "A lifecycle board: interested -> applied -> interview -> offer." },
  { icon: icons.lock, t: "Self-hosted & free", d: "Runs on free tiers, or one small box. Your data stays yours." },
];

const TABS = [
  { k: "Discovery", render: <MockDiscovery /> },
  { k: "Match report", render: <MockMatch /> },
  { k: "Fact-gate", render: <MockGate /> },
];
const STEPS = [
  { t: "Ingest", d: "Auto-onboard companies; poll their ATS boards; dedupe new postings." },
  { t: "Match", d: "Fit, gap, sponsorship, and keywords on the postings you track." },
  { t: "Tailor", d: "A grounded resume and cover letter, tailored to the posting." },
  { t: "Verify", d: "Fact-gate + ATS checks before anything ships." },
];

export default function LandingPage() {
  const [tab, setTab] = useState(0);
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

      {/* hero, left aligned, gradient 2nd line */}
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

      {/* primary features with inner mocks */}
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

      {/* tabbed preview (Supabase dashboard-tabs pattern) */}
      <section className="lp-section">
        <Reveal><h2 className="lp-h2"><span className="lp-h2-dim">See it in action,</span> from feed to fact-gate.</h2></Reveal>
        <Reveal i={1}>
          <div className="lp-tabs">
            {TABS.map((t, i) => (
              <button key={t.k} className={`lp-tab ${tab === i ? "on" : ""}`} onClick={() => setTab(i)}>{t.k}</button>
            ))}
          </div>
        </Reveal>
        <Reveal i={2}>
          <div className="lp-preview">
            <div className="lp-preview-bar"><span /><span /><span /></div>
            <div className="lp-preview-body">
              <AnimatePresence mode="wait">
                <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.28 }} className="lp-preview-inner">
                  {TABS[tab].render}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </Reveal>
      </section>

      {/* how it works */}
      <section className="lp-section" id="how">
        <Reveal><p className="lp-kicker mono">How it works</p></Reveal>
        <Reveal i={1}><h2 className="lp-h2">From a posting to a defensible application.</h2></Reveal>
        <div className="lp-steps">
          {STEPS.map((s, i) => (
            <Reveal key={s.t} i={i} className="lp-step">
              <div className="lp-step-n mono">{String(i + 1).padStart(2, "0")}</div>
              <div className="lp-step-t">{s.t}</div>
              <div className="lp-step-d">{s.d}</div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* open-source / self-host band */}
      <section className="lp-section">
        <div className="lp-os">
          <Reveal className="lp-os-l">
            <p className="lp-kicker mono">Open &amp; self-hosted</p>
            <h2 className="lp-h2">Own the whole stack. Free.</h2>
            <p className="lp-sub" style={{ margin: "10px 0 18px" }}>
              Deploy your own instance on Cloud Run, Turso, and Vercel within their free tiers, or run
              it locally with Docker. Read it, self-host it. You are never locked in.
            </p>
            <div className="lp-cta">
              <a className="btn btn-primary" href={REPO} target="_blank" rel="noreferrer">View on GitHub</a>
              <Link className="btn" href="/setup">Self-host guide</Link>
            </div>
          </Reveal>
          <Reveal i={1} className="lp-os-r">
            <div className="lp-stat"><b>$0</b><span>free-tier hostable</span></div>
            <div className="lp-stat"><b>100%</b><span>grounded to your profile</span></div>
            <div className="lp-stat"><b>1-click</b><span>capture + track</span></div>
            <div className="lp-stat"><b>0</b><span>auto-applies (human-in-loop)</span></div>
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
