"use client";
// Landing page (public `/`, RB.2). YC-SaaS style in the app's dark-navy + electric/cyan theme.
// Sections: nav · hero · demo-video slot · how-it-works · features · extension · self-host CTA ·
// footer. Scroll-reveal via framer-motion. A demo video can be dropped into the slot later.
import { motion, type Variants } from "framer-motion";
import Link from "next/link";
import type { ReactNode } from "react";

// --- scroll-reveal helper ---------------------------------------------------
const fadeUp: Variants = {
  hidden: { opacity: 0, y: 22 },
  show: (i: number = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.5, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] } }),
};
function Reveal({ children, i = 0, className }: { children: ReactNode; i?: number; className?: string }) {
  return (
    <motion.div className={className} variants={fadeUp} custom={i}
      initial="hidden" whileInView="show" viewport={{ once: true, margin: "-60px" }}>
      {children}
    </motion.div>
  );
}

// --- tiny stroke-SVG icons (match the sidebar idiom) ------------------------
const I = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round" width="22" height="22">{d}</svg>
);
const icons = {
  radar: I(<><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>),
  target: I(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="0.6" fill="currentColor" /></>),
  shield: I(<><path d="M12 3l7 3v6c0 4-3 6.5-7 9-4-2.5-7-5-7-9V6l7-3z" /><path d="M9 12l2 2 4-4" /></>),
  wand: I(<><path d="M15 4V2M15 10V8M11 6H9M19 6h-2" /><path d="M4 20l10-10 2 2L6 22z" /></>),
  globe: I(<><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>),
  puzzle: I(<><path d="M10 4a2 2 0 1 1 4 0v2h3a1 1 0 0 1 1 1v3h-2a2 2 0 1 0 0 4h2v3a1 1 0 0 1-1 1h-3v-2a2 2 0 1 0-4 0v2H7a1 1 0 0 1-1-1v-3H4a2 2 0 1 1 0-4h2V7a1 1 0 0 1 1-1h3V4z" /></>),
  bolt: I(<path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />),
  lock: I(<><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>),
};

const STEPS = [
  { t: "Ingest", d: "Auto-onboard companies; poll their ATS boards; dedupe new postings." },
  { t: "Match", d: "One-click track runs fit · gap · sponsorship · keywords — no résumé yet." },
  { t: "Tailor", d: "On demand: a grounded résumé + cover letter tailored to the posting." },
  { t: "Verify", d: "Mechanical fact-gate + ATS checks block anything you can't defend." },
];

const FEATURES = [
  { icon: icons.radar, t: "Deterministic Discovery", d: "A filterable, LLM-free feed of fresh postings — no misleading resume-fit ranking." },
  { icon: icons.target, t: "Match on demand", d: "Fit, gap analysis, sponsorship likelihood, and keywords — only when you choose to." },
  { icon: icons.puzzle, t: "One-click capture", d: "A browser extension grabs any posting (text + full-page screenshot) into your tracker." },
  { icon: icons.shield, t: "Anti-fabrication", d: "Every metric, employer, and title traces to your profile — a hard gate blocks the rest." },
  { icon: icons.globe, t: "Sponsorship-aware", d: "USCIS H-1B history + the JD's own stance feed the apply/no-apply decision." },
  { icon: icons.lock, t: "Self-hosted & free", d: "Runs on free tiers (Cloud Run · Turso · Vercel) or one small box. Your data stays yours." },
];

export default function LandingPage() {
  return (
    <div className="lp">
      {/* ambient */}
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
          <Link className="lp-navlink" href="/setup">Self-host</Link>
          <Link className="btn btn-sm btn-primary" href="/login">Login</Link>
        </nav>
      </header>

      {/* hero */}
      <section className="lp-hero">
        <motion.div initial="hidden" animate="show" variants={fadeUp} custom={0} className="lp-eyebrow mono">
          Self-hosted · Free · Grounded
        </motion.div>
        <motion.h1 initial="hidden" animate="show" variants={fadeUp} custom={1} className="lp-h1">
          Your job hunt, on autopilot —<br /><span className="lp-grad">without the fabrication.</span>
        </motion.h1>
        <motion.p initial="hidden" animate="show" variants={fadeUp} custom={2} className="lp-sub">
          ATS Resumaker watches the companies you care about, surfaces new roles, and turns any posting
          into a fact-checked, ATS-optimized résumé + cover letter — traced strictly to your real
          experience. Human-in-the-loop: it advises and drafts, it never auto-applies.
        </motion.p>
        <motion.div initial="hidden" animate="show" variants={fadeUp} custom={3} className="lp-cta">
          <Link className="btn btn-primary" href="/login">Get started</Link>
          <Link className="btn" href="/setup">Self-host guide →</Link>
        </motion.div>
      </section>

      {/* demo video slot */}
      <Reveal className="lp-video-wrap">
        <div className="lp-video" role="img" aria-label="Product demo (coming soon)">
          <div className="lp-video-inner">
            <span className="lp-play" aria-hidden>
              <svg viewBox="0 0 24 24" fill="currentColor" width="26" height="26"><path d="M8 5v14l11-7z" /></svg>
            </span>
            <span className="mono muted">demo walkthrough — coming soon</span>
          </div>
        </div>
      </Reveal>

      {/* how it works */}
      <section className="lp-section">
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

      {/* features */}
      <section className="lp-section">
        <Reveal><p className="lp-kicker mono">What you get</p></Reveal>
        <Reveal i={1}><h2 className="lp-h2">A full application platform, not just a résumé bot.</h2></Reveal>
        <div className="lp-grid-cards">
          {FEATURES.map((f, i) => (
            <Reveal key={f.t} i={i} className="lp-card">
              <span className="lp-card-ico">{f.icon}</span>
              <div className="lp-card-t">{f.t}</div>
              <div className="lp-card-d">{f.d}</div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* extension */}
      <section className="lp-section">
        <div className="lp-split">
          <Reveal className="lp-split-l">
            <span className="lp-card-ico">{icons.puzzle}</span>
            <h2 className="lp-h2" style={{ marginTop: 14 }}>Capture any posting in one click.</h2>
            <p className="lp-sub" style={{ margin: "10px 0 0" }}>
              The browser extension grabs the JD text and a full-page screenshot from the page you're
              already on — even auth-walled or JS-heavy sites — and tracks it. The backend skips
              server-side scraping and goes straight to the match.
            </p>
          </Reveal>
          <Reveal i={1} className="lp-split-r">
            <div className="lp-mini-window">
              <div className="lp-mini-bar"><span /><span /><span /></div>
              <div className="lp-mini-body">
                <div className="lp-mini-pill">⬡ Track</div>
                <div className="lp-mini-line" style={{ width: "72%" }} />
                <div className="lp-mini-line" style={{ width: "54%" }} />
                <div className="lp-mini-line" style={{ width: "63%" }} />
                <div className="lp-mini-toast mono">✓ tracked · full page</div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* self-host CTA */}
      <Reveal className="lp-cta-band">
        <span className="lp-card-ico">{icons.bolt}</span>
        <h2 className="lp-h2">Own the whole stack. Free.</h2>
        <p className="lp-sub" style={{ margin: "8px auto 18px", maxWidth: 560 }}>
          Deploy your own instance on Cloud Run + Turso + Vercel within their free tiers, or run it
          locally with Docker. A guided setup walks you through every step.
        </p>
        <div className="lp-cta" style={{ justifyContent: "center" }}>
          <Link className="btn btn-primary" href="/setup">Read the self-host guide</Link>
          <Link className="btn" href="/login">Login</Link>
        </div>
      </Reveal>

      {/* footer */}
      <footer className="lp-foot">
        <div className="lp-brand">
          <span className="rail-hex" aria-hidden style={{ width: 20, height: 20 }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" /></svg>
          </span>
          <b>ATS Resumaker</b>
        </div>
        <span className="mono muted">grounded · self-hostable · human-in-the-loop</span>
      </footer>
    </div>
  );
}
