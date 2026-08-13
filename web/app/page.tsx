"use client";
// Landing page (public `/`, RB.2). Supabase-inspired, in the app's dark-navy + electric/cyan theme.
// Sections: nav, hero, demo slot, feature cards (with inner mocks), a mini app-shell preview whose
// left nav swaps the right panel like the real platform, an animated how-it-works flow, an
// open/self-host band, and a final CTA. No AI-tell punctuation in the copy.
import { motion, type Variants } from "framer-motion";
import Link from "next/link";
import { type ReactNode } from "react";
import DemoConsole from "@/components/DemoConsole";

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

// ---- inner "mock" visuals for the secondary cards (in-theme, static) -------
const CvOnboard = () => (
  <div className="lp-cv lp-cv-onb">
    <span className="lp-cv-chip">Databricks</span>
    <svg className="lp-cv-ar" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
    <span className="lp-cv-chip alt">greenhouse.io/databricks</span>
    <em className="lp-cv-cost">$0</em>
  </div>
);
const CvCapture = () => (
  <div className="lp-cv lp-cv-cap">
    <span className="lp-cv-win"><i /><i /><i /><b /></span>
    <span className="lp-cv-clip">full-page capture</span>
  </div>
);
const CvSponsor = () => (
  <div className="lp-cv lp-cv-spon">
    <span className="lp-cv-h1b">H-1B history, 14 approvals</span>
    <span className="lp-cv-dec ok">apply</span>
    <span className="lp-cv-dec no">skip</span>
  </div>
);
const CvFree = () => (
  <div className="lp-cv lp-cv-free">
    {[["Cloud Run", 3], ["Storage", 2]].map(([k, v]) => (
      <div className="lp-cv-mrow" key={k as string}>
        <span>{k}</span><span className="lp-cv-mtrack"><i style={{ width: `${v}%` }} /></span><em>{v}%</em>
      </div>
    ))}
  </div>
);

const PRIMARY = [
  { icon: icons.radar, t: "Deterministic Discovery", d: "A filterable, LLM-free feed of fresh postings from companies you onboard, with no misleading resume-fit ranking.", mock: <MockDiscovery /> },
  { icon: icons.target, t: "Match, then tailor", d: "One click runs fit, gap, sponsorship, and keywords. Generate a grounded resume and cover letter only when you choose to.", mock: <MockMatch /> },
  { icon: icons.shield, t: "Anti-fabrication gate", d: "Every metric, employer, and title must trace to your profile. A mechanical gate blocks anything you cannot defend.", mock: <MockGate /> },
];
const SECONDARY = [
  { icon: icons.spark, t: "Agentic onboarding", d: "Give a company name and Claude resolves its ATS board automatically. $0 beyond your Claude subscription, or bring your own API key.", viz: <CvOnboard /> },
  { icon: icons.puzzle, t: "One-click capture", d: "A browser extension grabs any posting, text plus a full-page screenshot, into your tracker.", viz: <CvCapture /> },
  { icon: icons.globe, t: "Sponsorship-aware", d: "USCIS H-1B history and the posting's own stance drive the apply or skip call.", viz: <CvSponsor /> },
  { icon: icons.lock, t: "Self-hosted and free", d: "Runs on free tiers, or one small box. Your data stays yours.", viz: <CvFree /> },
];
const RAIL = ["Deterministic", "Grounded", "Sponsorship-aware", "One-click capture", "Self-hosted"];

// ---- how-it-works flow ------------------------------------------------------
const FLOW = [
  { icon: icons.spark, t: "Onboard", d: "You name a company. Claude CLI reads its careers page and resolves the ATS board, no config.", viz: "onboard" },
  { icon: icons.radar, t: "Ingest", d: "Every hour it polls the onboarded boards, dedupes, and surfaces only genuinely new roles.", viz: "ingest" },
  { icon: icons.target, t: "Match", d: "One click scans the posting, then an LLM scores fit with concrete haves and gaps.", viz: "match" },
  { icon: icons.wand, t: "Generate", d: "It drafts a resume and cover letter, every line traced to your real profile.", viz: "generate" },
  { icon: icons.check, t: "Apply", d: "You review, tweak, and apply. It never auto-applies. Human stays in the loop.", viz: "apply" },
];

// looping mini visual inside each how-it-works box
function FlowViz({ kind }: { kind: string }) {
  if (kind === "onboard") return (
    <div className="lp-fv lp-fv-chat">
      {[0, 1].map((i) => (
        <motion.span key={i} className={`lp-fv-bubble ${i ? "b" : "a"}`}
          animate={{ opacity: [0.25, 1, 0.25] }} transition={{ duration: 2.4, repeat: Infinity, delay: i * 1.2 }}>
          <i /><i /><i />
        </motion.span>
      ))}
    </div>
  );
  if (kind === "ingest") return (
    <div className="lp-fv lp-fv-ingest">
      {[0, 1, 2].map((i) => (
        <motion.span key={i} className="lp-fv-row"
          animate={{ opacity: [0, 1, 1, 0], x: [-8, 0, 0, 0] }} transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.35 }} />
      ))}
    </div>
  );
  if (kind === "match") return (
    <div className="lp-fv lp-fv-match">
      <motion.span className="lp-fv-scan" animate={{ y: [0, 30, 0] }} transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }} />
      <motion.b animate={{ opacity: [0, 0, 1, 1] }} transition={{ duration: 2.2, repeat: Infinity }}>71</motion.b>
    </div>
  );
  if (kind === "generate") return (
    <div className="lp-fv lp-fv-gen">
      {[0, 1, 2].map((i) => (
        <motion.span key={i} className="lp-fv-line"
          animate={{ width: ["0%", "80%"] }} transition={{ duration: 1.2, repeat: Infinity, repeatType: "reverse", delay: i * 0.2 }} />
      ))}
      <motion.span className="lp-fv-check" animate={{ scale: [0.6, 1, 0.6], opacity: [0, 1, 0] }} transition={{ duration: 2.4, repeat: Infinity }}>{icons.check}</motion.span>
    </div>
  );
  return (
    <div className="lp-fv lp-fv-apply">
      <motion.span className="lp-fv-stamp" animate={{ scale: [0.7, 1, 1, 0.7], opacity: [0, 1, 1, 0] }} transition={{ duration: 2.4, repeat: Infinity }}>{icons.check}</motion.span>
    </div>
  );
}

export default function LandingPage() {
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
        <div className="lp-hero-r">
          <motion.div className="lp-hviz" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
            <motion.div className="lp-hviz-card"
              animate={{ y: [0, -8, 0] }} transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}>
              <div className="lp-hviz-top"><span className="lp-hviz-logo" /><div><b>Databricks</b><span>AI Engineer</span></div>
                <span className="lp-hviz-badge">71</span></div>
              {[["skills", 83], ["experience", 63], ["domain", 77]].map(([k, v]) => (
                <div className="lp-hviz-meter" key={k as string}>
                  <span>{k}</span>
                  <span className="lp-hviz-track"><motion.span className="lp-hviz-fill"
                    initial={{ width: 0 }} animate={{ width: `${v}%` }} transition={{ delay: 0.5, duration: 1 }} /></span>
                </div>
              ))}
              <div className="lp-hviz-chips">{["Python", "RAG", "GCP", "FastAPI"].map((s) => <span key={s}>{s}</span>)}</div>
            </motion.div>
            <motion.div className="lp-hviz-float f1"
              animate={{ y: [0, -10, 0] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay: 0.4 }}>
              {icons.spark}<span>Agent onboarded a board</span><em>$0 extra</em>
            </motion.div>
            <motion.div className="lp-hviz-float f2"
              animate={{ y: [0, 9, 0] }} transition={{ duration: 4.6, repeat: Infinity, ease: "easeInOut", delay: 0.9 }}>
              {icons.check}<span>Traced to your profile</span>
            </motion.div>
          </motion.div>
          <motion.p initial="hidden" animate="show" variants={fadeUp} custom={1} className="lp-hero-copy">
            Watch the companies you care about, surface new roles, and turn any posting into a
            fact-checked, ATS-optimized resume and cover letter, traced strictly to your real
            experience. It advises and drafts; it never auto-applies.
          </motion.p>
        </div>
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
              {f.viz}
            </Reveal>
          ))}
        </div>
        <Reveal className="lp-rail">
          {RAIL.map((r, i) => (
            <span key={r} className="lp-rail-item mono">{r}{i < RAIL.length - 1 && <i aria-hidden>·</i>}</span>
          ))}
        </Reveal>
      </section>

      {/* interactive product console: auto-plays the workflow, then you drive it */}
      <section className="lp-section lp-section-wide">
        <Reveal><h2 className="lp-h2"><span className="lp-h2-dim">See it in action.</span> It plays the whole workflow, then it is yours to click.</h2></Reveal>
        <Reveal i={1}><p className="lp-sub" style={{ marginTop: 12 }}>Watch onboarding, ingestion, matching, the tailored report, and the digest run once, then take control and try it yourself.</p></Reveal>
        <Reveal i={2}><DemoConsole /></Reveal>
      </section>

      {/* how it works: animated flow */}
      <section className="lp-section" id="how">
        <Reveal><p className="lp-kicker mono">How it works</p></Reveal>
        <Reveal i={1}><h2 className="lp-h2">From a company name to a defensible application.</h2></Reveal>
        <div className="lp-flow">
          {FLOW.map((s, i) => (
            <div className="lp-flow-cell" key={s.t}>
              <Reveal i={i} className="lp-flow-box">
                <span className="lp-flow-n mono">{String(i + 1).padStart(2, "0")}</span>
                <span className="lp-flow-ico">{s.icon}</span>
                <div className="lp-flow-t">{s.t}</div>
                <div className="lp-flow-d">{s.d}</div>
                <FlowViz kind={s.viz} />
              </Reveal>
              {i < FLOW.length - 1 && (
                <motion.span className="lp-flow-arrow" aria-hidden
                  initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }}
                  transition={{ delay: i * 0.05 + 0.2 }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                  <motion.i className="lp-flow-dot" animate={{ x: [-2, 22], opacity: [0, 1, 0] }} transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.2 }} />
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
            <div className="lp-proof">
              <div className="lp-proof-head">
                <span className="lp-proof-h mono">Free-tier headroom, one user</span>
                <span className="lp-proof-live"><i />live estimate</span>
              </div>
              {[["Cloud Run", "240k vCPU-sec / mo", 3], ["Cloud Storage", "5 GB", 2], ["Turso", "3 GB syncs", 1], ["GitHub Actions", "2000 min / mo", 4]].map(([k, lim, v], idx) => (
                <div className="lp-proof-row" key={k as string}>
                  <span className="lp-proof-k">{k}</span>
                  <span className="lp-proof-track"><motion.i initial={{ width: 0 }} whileInView={{ width: `${v}%` }} viewport={{ once: true }} transition={{ delay: idx * 0.08, duration: 0.8 }} /></span>
                  <span className="lp-proof-v mono">{v}%</span>
                  <span className="lp-proof-lim mono">{lim}</span>
                </div>
              ))}
              <div className="lp-proof-foot">
                <span><b>$0</b> / month</span>
                <span className="mono">0 auto-applies, human in the loop</span>
              </div>
            </div>
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
