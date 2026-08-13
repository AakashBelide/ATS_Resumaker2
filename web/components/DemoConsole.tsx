"use client";
// Landing "See it in action" console. A mac-window mock of the real platform that loops through the
// whole workflow (onboard -> ingest -> discover -> track -> report -> dashboard -> mailer -> profile)
// until the visitor takes control, after which they can click it themselves and replay the tour.
// All mock, self-contained, no network.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";

/* ---- tiny icon set --------------------------------------------------------- */
const S = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round">{d}</svg>
);
const ic = {
  discovery: S(<><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>),
  tracker: S(<><rect x="3" y="4" width="7" height="16" rx="1" /><rect x="14" y="4" width="7" height="10" rx="1" /></>),
  onboard: S(<><path d="M9 15l6-6M10 5l1-1a4 4 0 0 1 6 6l-1 1M14 19l-1 1a4 4 0 0 1-6-6l1-1" /></>),
  dashboard: S(<><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></>),
  mailer: S(<><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M4 7l8 6 8-6" /></>),
  profile: S(<><circle cx="12" cy="8" r="4" /><path d="M4.5 21c0-4 3.6-6 7.5-6s7.5 2 7.5 6" /></>),
  check: S(<path d="M20 6L9 17l-5-5" />),
  spark: S(<path d="M12 3l1.7 5.1L19 10l-5.3 1.9L12 17l-1.7-5.1L5 10l5.3-1.9L12 3z" />),
  back: S(<path d="M15 6l-6 6 6 6" />),
  doc: S(<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>),
  scan: S(<><path d="M4 8V5a1 1 0 0 1 1-1h3M20 8V5a1 1 0 0 0-1-1h-3M4 16v3a1 1 0 0 0 1 1h3M20 16v3a1 1 0 0 1-1 1h-3" /></>),
  copy: S(<><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></>),
  image: S(<><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="M21 15l-5-5L5 21" /></>),
  clock: S(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>),
  x: S(<path d="M18 6L6 18M6 6l12 12" />),
  menu: S(<path d="M4 6h16M4 12h16M4 18h16" />),
};

/* ---- data ------------------------------------------------------------------ */
type Lvl = "junior" | "mid" | "senior";
type Posting = { id: string; company: string; role: string; lvl: Lvl; age: number; fit: number };
const POSTINGS: Posting[] = [
  { id: "databricks", company: "Databricks", role: "AI Engineer", lvl: "junior", age: 1, fit: 71 },
  { id: "ramp", company: "Ramp", role: "ML Engineer", lvl: "mid", age: 1, fit: 63 },
  { id: "anthropic", company: "Anthropic", role: "Research Engineer", lvl: "senior", age: 1, fit: 52 },
  { id: "stripe", company: "Stripe", role: "ML Engineer", lvl: "senior", age: 1, fit: 55 },
  { id: "baselayer", company: "Baselayer", role: "AI Engineer", lvl: "junior", age: 2, fit: 68 },
  { id: "scale", company: "Scale AI", role: "ML Engineer", lvl: "mid", age: 3, fit: 60 },
  { id: "notion", company: "Notion", role: "AI Engineer", lvl: "junior", age: 5, fit: 66 },
];

type Report = {
  subs: { k: string; v: number }[]; haves: string[]; gaps: string[];
  skills: string[]; jd: string; resume: string[]; cover: string; sponsor: string;
};
function buildReport(company: string, role: string, fit: number): Report {
  return {
    subs: [
      { k: "skills", v: Math.min(95, fit + 12) },
      { k: "experience", v: Math.max(40, fit - 8) },
      { k: "domain", v: Math.min(92, fit + 6) },
      { k: "sponsorship", v: company === "Ramp" ? 30 : 80 },
    ],
    haves: [
      "Python, FastAPI, production LLM services",
      "RAG and retrieval evaluation, shipped to users",
      "GCP, Cloud Run, Airflow, event-driven pipelines",
    ],
    gaps: [
      "Kubernetes at scale (posting asks, profile is light)",
      "5+ yrs requested, you have 3 (fit adjusted, not hidden)",
    ],
    skills: ["Python", "FastAPI", "RAG", "LangGraph", "GCP", "Airflow", "Prompt Eng", "Evals"],
    jd: `${company} is hiring a ${role} to build LLM-backed features end to end: retrieval, evaluation, and reliable serving. You will own data pipelines and ship to production with a small team.`,
    resume: [
      "Built a retrieval-augmented assistant on FastAPI + GCP serving 40k monthly queries at p95 under 900ms.",
      "Cut hallucinated answers 38% with a grounded-citation eval harness gating every release.",
      "Owned Airflow ingestion for 7 sources, dedupe and backfill, 99.9% freshness.",
    ],
    cover: `I am applying for the ${role} role at ${company}. My work centers on grounded LLM systems: retrieval, evaluation, and dependable serving, exactly the loop your posting describes. Every claim here traces to work I actually shipped.`,
    sponsor: company === "Ramp" ? "No sponsorship signalled, flagged before you spend effort" : "Sponsors H-1B, 14 approvals in USCIS history",
  };
}

type Tracked = { key: string; company: string; role: string; lvl: Lvl; fit: number; stage: string; loading: boolean; report: Report };
// seed companies deliberately do NOT overlap with the Discovery feed
const seedTracked = (): Tracked[] => [
  { key: "morgan", company: "Morgan Stanley", role: "AI Engineer", lvl: "mid", fit: 68, stage: "applied", loading: false, report: buildReport("Morgan Stanley", "AI Engineer", 68) },
  { key: "datadog", company: "Datadog", role: "ML Engineer", lvl: "mid", fit: 61, stage: "interview", loading: false, report: buildReport("Datadog", "ML Engineer", 61) },
  { key: "plaid", company: "Plaid", role: "AI Engineer", lvl: "junior", fit: 57, stage: "interested", loading: false, report: buildReport("Plaid", "AI Engineer", 57) },
];
const seedBoards = () => [{ name: "Stripe", on: true }, { name: "Anthropic", on: true }, { name: "Notion", on: false }];

const DAILY = [8, 12, 6, 15, 11, 9, 14];
const DOW = ["M", "T", "W", "T", "F", "S", "S"];

const TABS = [
  { key: "discovery", label: "Discovery", icon: ic.discovery },
  { key: "tracker", label: "Tracker", icon: ic.tracker },
  { key: "onboard", label: "Onboarding", icon: ic.onboard },
  { key: "dashboard", label: "Dashboard", icon: ic.dashboard },
  { key: "mailer", label: "Mailer", icon: ic.mailer },
  { key: "profile", label: "Profile", icon: ic.profile },
];

/* ---- component ------------------------------------------------------------- */
export default function DemoConsole() {
  const [tab, setTab] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  const [auto, setAuto] = useState(true);
  const [pressed, setPressed] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [report, setReport] = useState<Tracked | null>(null);

  const [levels, setLevels] = useState<Record<Lvl, boolean>>({ junior: true, mid: true, senior: false });
  const [days, setDays] = useState(1);
  const [tracked, setTracked] = useState<Tracked[]>(seedTracked);
  const [boards, setBoards] = useState(seedBoards);
  const [onbText, setOnbText] = useState("");
  const [onbStatus, setOnbStatus] = useState<"idle" | "resolving" | "done">("idle");
  const [onbSteps, setOnbSteps] = useState<string[]>([]);
  const [freq, setFreq] = useState<string>("hourly");
  const [mailLevels, setMailLevels] = useState<Record<Lvl, boolean>>({ junior: true, mid: true, senior: false });
  const [include, setInclude] = useState<string[]>(["LLM", "RAG", "Python"]);
  const [exclude, setExclude] = useState<string[]>(["clearance", "senior"]);
  const [quietFrom, setQuietFrom] = useState("22:00");
  const [quietTo, setQuietTo] = useState("07:00");

  const timers = useRef<number[]>([]);
  const waiters = useRef<Array<() => void>>([]);
  const genRef = useRef(0);          // current tour generation; bumping it cancels the running loop
  const runningRef = useRef(false);  // a tour loop is currently active
  const controlRef = useRef(false);  // visitor took control, do not auto-restart
  const reportScroll = useRef<HTMLDivElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const wait = (ms: number) => new Promise<void>((res) => { const id = window.setTimeout(res, ms); timers.current.push(id); waiters.current.push(res); });
  const flush = () => { timers.current.forEach(clearTimeout); timers.current = []; waiters.current.splice(0).forEach((r) => r()); };

  const visible = POSTINGS.filter((p) => levels[p.lvl] && p.age <= days);
  const trackedKeys = new Set(tracked.map((t) => t.key));

  function trackPosting(p: Posting) {
    setTracked((prev) => (prev.some((t) => t.key === p.id) ? prev
      : [...prev, { key: p.id, company: p.company, role: p.role, lvl: p.lvl, fit: p.fit, stage: "interested", loading: true, report: buildReport(p.company, p.role, p.fit) }]));
    setTab(1);
    const id = window.setTimeout(() => setTracked((prev) => prev.map((t) => (t.key === p.id ? { ...t, loading: false } : t))), 1400);
    timers.current.push(id);
  }

  function takeControl() {
    if (!auto) return;
    controlRef.current = true; genRef.current++; runningRef.current = false; flush();
    setAuto(false); setIngesting(false); setPressed("");
    setTracked((prev) => prev.map((t) => ({ ...t, loading: false })));
  }

  function resetSlate() {
    setReport(null); setIngesting(false); setPressed("");
    setLevels({ junior: true, mid: true, senior: false }); setDays(1);
    setTracked(seedTracked()); setBoards(seedBoards());
    setOnbText(""); setOnbStatus("idle"); setOnbSteps([]);
    setFreq("hourly"); setMailLevels({ junior: true, mid: true, senior: false });
    setInclude(["LLM", "RAG", "Python"]); setExclude(["clearance", "senior"]);
    setQuietFrom("22:00"); setQuietTo("07:00"); setTab(0);
  }

  async function playOnce(dead: () => boolean): Promise<boolean> {
    setTab(2); await wait(700); if (dead()) return false;
    const name = "Databricks";
    for (let i = 1; i <= name.length; i++) { setOnbText(name.slice(0, i)); await wait(60); if (dead()) return false; }
    await wait(350);
    setPressed("onb-go"); await wait(200); setPressed(""); setOnbStatus("resolving");
    for (const st of ["Reading the careers page", "Found board at greenhouse.io/databricks", "Confirmed roles are live, adding to watchlist"]) {
      setOnbSteps((p) => [...p, st]); await wait(820); if (dead()) return false;
    }
    setOnbStatus("done");
    setBoards((p) => (p.some((b) => b.name === "Databricks") ? p : [...p, { name: "Databricks", on: true }]));
    await wait(1100); if (dead()) return false;

    setTab(0); setIngesting(true); await wait(1300); if (dead()) return false;
    setIngesting(false); await wait(600); if (dead()) return false;
    setPressed("days-7"); await wait(200); setPressed(""); setDays(7); await wait(1100); if (dead()) return false;

    setPressed("track-databricks"); await wait(260); setPressed("");
    trackPosting(POSTINGS[0]); await wait(1900); if (dead()) return false;

    setPressed("report-databricks"); await wait(220); setPressed("");
    setTracked((prev) => { const f = prev.find((t) => t.key === "databricks"); if (f) setReport(f); return prev; });
    await wait(650); autoScrollReport(dead); await wait(3200); if (dead()) return false;
    setReport(null); await wait(500); if (dead()) return false;

    setTab(3); await wait(2400); if (dead()) return false;
    setTab(4); await wait(900); setFreq("every 4 hours"); await wait(1700); if (dead()) return false;
    setTab(5); await wait(1900); if (dead()) return false;

    setTab(0); await wait(2600); if (dead()) return false;
    return true;
  }

  async function runTour() {
    const gen = ++genRef.current;            // invalidate any prior loop
    const dead = () => gen !== genRef.current;
    controlRef.current = false; runningRef.current = true; setAuto(true);
    while (!dead()) { flush(); resetSlate(); const ok = await playOnce(dead); if (!ok) break; }
    if (gen === genRef.current) runningRef.current = false;
  }

  function autoScrollReport(dead: () => boolean) {
    const el = reportScroll.current; if (!el) return;
    const max = el.scrollHeight - el.clientHeight; if (max <= 0) return;
    let y = 0;
    const step = () => { if (dead() || !reportScroll.current) return; y = Math.min(y + max / 44, max); el.scrollTop = y; if (y < max) { const id = window.setTimeout(step, 45); timers.current.push(id); } };
    step();
  }

  useEffect(() => {
    const node = rootRef.current; if (!node) return;
    const obs = new IntersectionObserver((e) => {
      if (e[0].isIntersecting && !controlRef.current && !runningRef.current) runTour();
    }, { threshold: 0.25 });
    obs.observe(node);
    return () => { obs.disconnect(); genRef.current++; runningRef.current = false; flush(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onboardNow() {
    const name = onbText.trim(); if (!name || onbStatus === "resolving") return;
    setOnbStatus("resolving"); setOnbSteps([]);
    for (const st of ["Reading the careers page", `Resolved ATS board for ${name}`, "Roles are live, added to watchlist"]) {
      setOnbSteps((p) => [...p, st]); await wait(700);
    }
    setOnbStatus("done");
    setBoards((p) => (p.some((b) => b.name.toLowerCase() === name.toLowerCase()) ? p : [...p, { name, on: true }]));
  }

  const goTab = (i: number) => { takeControl(); setReport(null); setTab(i); setNavOpen(false); };

  return (
    <div className="dc" ref={rootRef}>
      <div className="dc-bar">
        <span className="dc-dot r" /><span className="dc-dot y" /><span className="dc-dot g" />
        <em className="mono">ats-resumaker</em>
        <div className="dc-bar-right">
          {auto
            ? <button className="dc-tourbadge" onClick={takeControl}><span className="dc-live" /><span className="dc-tb-full">Auto tour playing, click to take control</span><span className="dc-tb-min">Auto tour</span></button>
            : <button className="dc-replay" onClick={runTour}>{ic.spark}<span className="dc-tb-full">Replay tour</span><span className="dc-tb-min">Replay</span></button>}
          <button className="dc-menu" onClick={() => setNavOpen((o) => !o)} aria-label="menu">{navOpen ? ic.x : ic.menu}</button>
        </div>
      </div>

      <div className="dc-body">
        {navOpen && <div className="dc-nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden />}
        <nav className={`dc-nav ${navOpen ? "open" : ""}`}>
          {TABS.map((t, i) => (
            <button key={t.key} className={`dc-navitem ${tab === i ? "on" : ""}`} onClick={() => goTab(i)}>
              <span className="ico">{t.icon}</span><span>{t.label}</span>
            </button>
          ))}
          <div className="dc-nav-foot"><span className="dc-nav-user"><span className="dc-avatar" />Aakash</span></div>
        </nav>

        <div className="dc-main">
          <AnimatePresence mode="wait">
            {report ? (
              <motion.div key="report" className="dc-scroll" ref={reportScroll}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                <ReportView t={report} onBack={() => setReport(null)} />
              </motion.div>
            ) : (
              <motion.div key={tab} className="dc-scroll"
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.22 }}>
                {tab === 0 && (
                  <Discovery visible={visible} levels={levels} days={days} ingesting={ingesting} pressed={pressed} trackedKeys={trackedKeys}
                    onLevel={(l) => { takeControl(); setLevels((p) => ({ ...p, [l]: !p[l] })); }}
                    onDays={(d) => { takeControl(); setDays(d); }}
                    onTrack={(p) => { takeControl(); trackPosting(p); }} />
                )}
                {tab === 1 && <TrackerView tracked={tracked} pressed={pressed} onReport={(t) => { takeControl(); setReport(t); }} />}
                {tab === 2 && (
                  <OnboardView text={onbText} status={onbStatus} steps={onbSteps} boards={boards} pressed={pressed}
                    onText={(v) => { takeControl(); setOnbText(v); }}
                    onGo={() => { takeControl(); onboardNow(); }}
                    onToggle={(n) => { takeControl(); setBoards((p) => p.map((b) => (b.name === n ? { ...b, on: !b.on } : b))); }} />
                )}
                {tab === 3 && <DashboardView tracked={tracked} boards={boards} />}
                {tab === 4 && (
                  <MailerView freq={freq} mailLevels={mailLevels} include={include} exclude={exclude} quietFrom={quietFrom} quietTo={quietTo}
                    onFreq={(f) => { takeControl(); setFreq(f); }}
                    onLevel={(l) => { takeControl(); setMailLevels((p) => ({ ...p, [l]: !p[l] })); }}
                    onAddInclude={(k) => { takeControl(); setInclude((p) => (p.includes(k) ? p : [...p, k])); }}
                    onDelInclude={(k) => { takeControl(); setInclude((p) => p.filter((x) => x !== k)); }}
                    onAddExclude={(k) => { takeControl(); setExclude((p) => (p.includes(k) ? p : [...p, k])); }}
                    onDelExclude={(k) => { takeControl(); setExclude((p) => p.filter((x) => x !== k)); }}
                    onQuiet={(f, t) => { takeControl(); setQuietFrom(f); setQuietTo(t); }} />
                )}
                {tab === 5 && <ProfileView />}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

/* ---- panels ---------------------------------------------------------------- */
function Discovery({ visible, levels, days, ingesting, pressed, trackedKeys, onLevel, onDays, onTrack }: {
  visible: Posting[]; levels: Record<Lvl, boolean>; days: number; ingesting: boolean; pressed: string; trackedKeys: Set<string>;
  onLevel: (l: Lvl) => void; onDays: (d: number) => void; onTrack: (p: Posting) => void;
}) {
  return (
    <div className="dc-pane">
      <div className="dc-pane-head"><h4>Discovery</h4><span className="dc-count">{visible.length} roles</span></div>
      <div className="dc-filters">
        <span className="dc-fgrp">{(["junior", "mid", "senior"] as Lvl[]).map((l) => (
          <button key={l} className={`dc-pill ${levels[l] ? "on" : ""}`} onClick={() => onLevel(l)}>{l}</button>))}</span>
        <span className="dc-fgrp">{[1, 7, 30].map((d) => (
          <button key={d} className={`dc-pill ${days === d ? "on" : ""} ${pressed === `days-${d}` ? "press" : ""}`} onClick={() => onDays(d)}>{d}d</button>))}</span>
      </div>
      {ingesting && <div className="dc-ingest"><span className="dc-live" />Hourly ingest running, polling onboarded boards</div>}
      <div className="dc-jobs">
        <AnimatePresence>
          {visible.map((p, i) => {
            const isTracked = trackedKeys.has(p.id);
            return (
              <motion.div key={p.id} layout className="dc-job"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
                transition={{ delay: ingesting ? 0 : i * 0.04, duration: 0.28 }}>
                <span className="dc-logo" />
                <div className="dc-job-txt">
                  <span className="dc-job-t">{p.company} <i>{p.role}</i></span>
                  <span className="dc-job-meta">{p.lvl} · {p.age}d ago · onboarded board</span>
                </div>
                {isTracked
                  ? <span className="dc-track tracked">{ic.check} Tracked</span>
                  : <button className={`dc-track ${pressed === `track-${p.id}` ? "press" : ""}`} onClick={() => onTrack(p)}>+ Track</button>}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}

function TrackerView({ tracked, pressed, onReport }: { tracked: Tracked[]; pressed: string; onReport: (t: Tracked) => void }) {
  return (
    <div className="dc-pane">
      <div className="dc-pane-head"><h4>Tracker</h4><span className="dc-count">{tracked.length} tracked</span></div>
      <div className="dc-thead"><span>Company</span><span>Role</span><span className="c">Fit</span><span>Stage</span><span /></div>
      {tracked.map((t) => (
        <div className="dc-trow" key={t.key}>
          <span className="dc-tco"><span className="dc-logo sm" />{t.company}</span>
          <span className="dim">{t.role}</span>
          <span className="c">{t.loading ? <span className="dc-shimmer" /> : <b className={`dc-fit ${t.fit >= 65 ? "hi" : t.fit >= 50 ? "mid" : "lo"}`}>{t.fit}</b>}</span>
          <span>{t.loading ? <span className="dc-shimmer wide" /> : <span className="dc-stage">{t.stage}</span>}</span>
          <span className="r"><button className={`dc-linkbtn ${pressed === `report-${t.key}` ? "press" : ""}`} disabled={t.loading} onClick={() => onReport(t)}>Report</button></span>
        </div>
      ))}
      {tracked.some((t) => t.loading) && <div className="dc-matching"><span className="dc-live" />Matching against your profile, scoring fit and gaps</div>}
    </div>
  );
}

function ReportView({ t, onBack }: { t: Tracked; onBack: () => void }) {
  const r = t.report;
  const [doc, setDoc] = useState<"resume" | "cover" | "shot">("resume");
  const [copied, setCopied] = useState(false);
  return (
    <div className="dc-report">
      <button className="dc-back" onClick={onBack}>{ic.back}Back to tracker</button>
      <div className="dc-rep-head">
        <div><div className="dc-rep-co">{t.company} <i>{t.role}</i></div><div className="dc-rep-sub">{r.sponsor}</div></div>
        <div className={`dc-rep-score ${t.fit >= 65 ? "hi" : "mid"}`}><b>{t.fit}</b><small>/100</small></div>
      </div>

      <div className="dc-rep-split">
        {/* LEFT: analysis */}
        <div className="dc-rep-left">
          <div className="dc-rep-meters">
            {r.subs.map((s) => (
              <div className="dc-meter" key={s.k}>
                <span className="dc-meter-l">{s.k}</span>
                <span className="dc-meter-t"><motion.span className="dc-meter-f" initial={{ width: 0 }} animate={{ width: `${s.v}%` }} transition={{ duration: 0.7 }} /></span>
                <span className="dc-meter-v">{s.v}</span>
              </div>
            ))}
          </div>
          <div className="dc-rep-card ok"><h5>{ic.check} You have</h5><ul>{r.haves.map((h) => <li key={h}>{h}</li>)}</ul></div>
          <div className="dc-rep-card gap"><h5>Gaps to address</h5><ul>{r.gaps.map((g) => <li key={g}>{g}</li>)}</ul></div>
          <div className="dc-rep-chips">{r.skills.map((s) => <span key={s}>{s}</span>)}</div>
          <div className="dc-rep-block"><h5>{ic.doc} Job description</h5><p>{r.jd}</p></div>
        </div>

        {/* RIGHT: generated artifacts with a switcher */}
        <div className="dc-rep-right">
          <div className="dc-docswitch">
            <button className={doc === "resume" ? "on" : ""} onClick={() => setDoc("resume")}>{ic.doc}Resume</button>
            <button className={doc === "cover" ? "on" : ""} onClick={() => setDoc("cover")}>{ic.mailer}Cover</button>
            <button className={doc === "shot" ? "on" : ""} onClick={() => setDoc("shot")}>{ic.image}Screenshot</button>
          </div>
          <AnimatePresence mode="wait">
            <motion.div key={doc} className="dc-docview" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
              {doc === "resume" && (
                <div className="dc-paper">
                  <div className="dc-paper-name" />
                  <div className="dc-paper-contact" />
                  {["Experience", "Projects", "Skills"].map((sec, si) => (
                    <div className="dc-paper-sec" key={sec}>
                      <span className="dc-paper-h">{sec}</span>
                      {Array.from({ length: si === 2 ? 2 : 3 }).map((_, i) => <span key={i} className="dc-paper-line" style={{ width: `${94 - i * 12}%` }} />)}
                    </div>
                  ))}
                  <span className="dc-paper-tag">grounded to profile.json</span>
                </div>
              )}
              {doc === "cover" && (
                <div className="dc-paper">
                  <button className="dc-copy" onClick={() => { setCopied(true); }}>{copied ? ic.check : ic.copy}{copied ? "Copied" : "Copy"}</button>
                  <div className="dc-paper-name sm" />
                  {Array.from({ length: 9 }).map((_, i) => <span key={i} className="dc-paper-line" style={{ width: `${[96, 92, 88, 94, 70, 90, 86, 93, 55][i]}%` }} />)}
                  <span className="dc-paper-tag">copy only, no fabricated claims</span>
                </div>
              )}
              {doc === "shot" && (
                <div className="dc-shot">
                  <div className="dc-shot-bar"><span className="r" /><span className="y" /><span className="g" /><em>{t.company.toLowerCase()} · careers</em></div>
                  <div className="dc-shot-body">
                    <span className="dc-shot-title" />
                    {Array.from({ length: 8 }).map((_, i) => <span key={i} className="dc-shot-line" style={{ width: `${92 - (i % 3) * 16}%` }} />)}
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function OnboardView({ text, status, steps, boards, pressed, onText, onGo, onToggle }: {
  text: string; status: "idle" | "resolving" | "done"; steps: string[]; boards: { name: string; on: boolean }[];
  pressed: string; onText: (v: string) => void; onGo: () => void; onToggle: (n: string) => void;
}) {
  return (
    <div className="dc-pane">
      <div className="dc-pane-head"><h4>Onboarding</h4><span className="dc-count">agentic, no config</span></div>
      <div className="dc-onb-form">
        <input className="dc-input" placeholder="Company name, e.g. Databricks" value={text} onChange={(e) => onText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onGo()} />
        <button className={`dc-btn ${pressed === "onb-go" ? "press" : ""}`} onClick={onGo} disabled={status === "resolving"}>{status === "resolving" ? "Resolving." : "Onboard"}</button>
      </div>
      <div className="dc-agent">
        <div className="dc-agent-head">{ic.spark}<span>Claude CLI is resolving the ATS board</span></div>
        <div className="dc-agent-steps">
          {steps.map((st, i) => (<motion.div key={i} className="dc-agent-step" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}><span className="dc-agent-ok">{ic.check}</span>{st}</motion.div>))}
          {status === "resolving" && <div className="dc-agent-step typing"><span className="dc-typing"><i /><i /><i /></span></div>}
          {status === "done" && <div className="dc-agent-done">Onboarded. Ingestion will poll it hourly.</div>}
        </div>
      </div>
      <div className="dc-boards-h">Onboarded boards, toggle ingestion per company</div>
      <div className="dc-boards">
        {boards.map((b) => (
          <div className="dc-board" key={b.name}>
            <span className="dc-logo sm" /><span className="dc-board-n">{b.name}</span>
            <button className={`dc-toggle ${b.on ? "on" : ""}`} onClick={() => onToggle(b.name)} aria-label="toggle ingestion"><span /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function DashboardView({ tracked, boards }: { tracked: Tracked[]; boards: { name: string; on: boolean }[] }) {
  const applied = tracked.filter((t) => t.stage === "applied").length;
  const avg = Math.round(tracked.reduce((a, t) => a + t.fit, 0) / Math.max(1, tracked.length));
  const max = Math.max(...DAILY);
  return (
    <div className="dc-pane">
      <div className="dc-pane-head"><h4>Dashboard</h4><span className="dc-count">last 7 days</span></div>
      <div className="dc-kpis">
        {[["14", "postings today"], [String(tracked.length), "tracked"], [String(applied), "applied"], [`${avg}`, "avg fit"], [String(boards.filter((b) => b.on).length), "active boards"]].map(([n, l]) => (
          <div className="dc-kpi" key={l}><b>{n}</b><span>{l}</span></div>))}
      </div>
      <div className="dc-chart-card">
        <div className="dc-chart-h">New postings per day</div>
        <div className="dc-chart">
          {DAILY.map((v, i) => (
            <div className="dc-bar-col" key={i}>
              <motion.span className="dc-cbar" initial={{ height: 0 }} animate={{ height: `${(v / max) * 100}%` }} transition={{ delay: i * 0.05, duration: 0.5 }} />
              <em>{DOW[i]}</em>
            </div>))}
        </div>
      </div>
      <div className="dc-toplist">
        <div className="dc-chart-h">Most active boards</div>
        {[["Databricks", 14], ["Stripe", 11], ["Anthropic", 9]].map(([n, c]) => (
          <div className="dc-toprow" key={n as string}><span className="dc-logo sm" /><span>{n}</span><b>{c} roles</b></div>))}
      </div>
    </div>
  );
}

function MailerView({ freq, mailLevels, include, exclude, quietFrom, quietTo, onFreq, onLevel, onAddInclude, onDelInclude, onAddExclude, onDelExclude, onQuiet }: {
  freq: string; mailLevels: Record<Lvl, boolean>; include: string[]; exclude: string[]; quietFrom: string; quietTo: string;
  onFreq: (f: string) => void; onLevel: (l: Lvl) => void;
  onAddInclude: (k: string) => void; onDelInclude: (k: string) => void; onAddExclude: (k: string) => void; onDelExclude: (k: string) => void;
  onQuiet: (f: string, t: string) => void;
}) {
  const [inc, setInc] = useState(""); const [exc, setExc] = useState("");
  const times = ["06:00", "07:00", "08:00", "18:00", "20:00", "21:00", "22:00", "23:00"];
  const FREQS = ["hourly", "every 2 hours", "every 4 hours", "every 8 hours", "daily", "off"];
  const pool = [
    { co: "Databricks", role: "AI Engineer", lvl: "junior", tags: ["llm", "rag", "python"] },
    { co: "Notion", role: "AI Engineer", lvl: "junior", tags: ["llm", "python"] },
    { co: "Ramp", role: "ML Engineer", lvl: "mid", tags: ["ml", "python"] },
    { co: "Anthropic", role: "Research Engineer", lvl: "senior", tags: ["research", "llm"] },
  ];
  const inc_l = include.map((k) => k.toLowerCase()); const exc_l = exclude.map((k) => k.toLowerCase());
  const matches = pool.filter((p) => mailLevels[p.lvl as Lvl]
    && (inc_l.length === 0 || p.tags.some((t) => inc_l.includes(t)))
    && !exc_l.some((k) => p.lvl === k || p.role.toLowerCase().includes(k) || p.tags.includes(k)));
  return (
    <div className="dc-pane">
      <div className="dc-pane-head"><h4>Email digest</h4><span className="dc-count">delivered to you</span></div>
      <div className="dc-field"><label>Frequency</label>
        <select className="dc-select" value={freq} onChange={(e) => onFreq(e.target.value)}>
          {FREQS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>
      <div className="dc-field"><label>Levels</label>
        <div className="dc-fgrp">{(["junior", "mid", "senior"] as Lvl[]).map((l) => (
          <button key={l} className={`dc-pill ${mailLevels[l] ? "on" : ""}`} onClick={() => onLevel(l)}>{l}</button>))}</div>
      </div>
      <div className="dc-field"><label>Title should include</label>
        <div className="dc-kwrow">
          {include.map((k) => <span className="dc-kw inc" key={k}>{k}<button onClick={() => onDelInclude(k)} aria-label="remove">{ic.x}</button></span>)}
          <input className="dc-kwadd" placeholder="add keyword" value={inc} onChange={(e) => setInc(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && inc.trim()) { onAddInclude(inc.trim()); setInc(""); } }} />
        </div>
      </div>
      <div className="dc-field"><label>Title should not include</label>
        <div className="dc-kwrow">
          {exclude.map((k) => <span className="dc-kw exc" key={k}>{k}<button onClick={() => onDelExclude(k)} aria-label="remove">{ic.x}</button></span>)}
          <input className="dc-kwadd" placeholder="add keyword" value={exc} onChange={(e) => setExc(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && exc.trim()) { onAddExclude(exc.trim()); setExc(""); } }} />
        </div>
      </div>
      <div className="dc-field"><label>{ic.clock} Quiet hours, no mail between</label>
        <div className="dc-quiet">
          <select value={quietFrom} onChange={(e) => onQuiet(e.target.value, quietTo)}>{times.map((t) => <option key={t}>{t}</option>)}</select>
          <span>to</span>
          <select value={quietTo} onChange={(e) => onQuiet(quietFrom, e.target.value)}>{times.map((t) => <option key={t}>{t}</option>)}</select>
        </div>
      </div>
      <div className="dc-mail-prev">
        <div className="dc-mail-top"><span className="dc-logo sm" /><b>ATS Resumaker</b><em>{freq === "off" ? "paused" : freq}</em></div>
        <div className="dc-mail-sub">{matches.length} new roles match your filters{freq === "off" ? ", digest paused" : `, sent ${freq}, outside ${quietFrom} to ${quietTo}`}</div>
        {matches.slice(0, 3).map((m) => (<div className="dc-mail-row" key={m.co + m.role}><span>{m.co} <i>{m.role}</i></span><span className="dc-mail-lvl">{m.lvl}</span></div>))}
        {freq === "off" && <div className="dc-mail-off">Digest paused, turn on daily or weekly to resume.</div>}
      </div>
    </div>
  );
}

function ProfileView() {
  return (
    <div className="dc-pane">
      <div className="dc-pane-head"><h4>Profile</h4><span className="dc-count">your source of truth</span></div>
      <div className="dc-prof-stats"><div><b>3</b><span>yrs experience</span></div><div><b>7</b><span>employers</span></div><div><b>70</b><span>skills</span></div></div>
      <div className="dc-field"><label>Skills, extracted from your history</label>
        <div className="dc-prof-chips">{["Python", "FastAPI", "RAG", "LangGraph", "GCP", "Airflow", "Snowflake", "Prompt Eng", "Evals", "Terraform", "Cloud Run", "Playwright"].map((s) => <span key={s}>{s}</span>)}</div>
      </div>
      <div className="dc-agent">
        <div className="dc-agent-head">{ic.spark}<span>Profile chat agent</span></div>
        <div className="dc-agent-steps">
          <div className="dc-agent-step"><span className="dc-agent-ok">{ic.check}</span>Suggested: add metric to the Bajaj role, revenue impact</div>
          <div className="dc-agent-step"><span className="dc-agent-ok">{ic.check}</span>You approve, decline, or edit before it is saved</div>
          <div className="dc-agent-done">Every generated line traces back here. Nothing is invented.</div>
        </div>
      </div>
    </div>
  );
}
