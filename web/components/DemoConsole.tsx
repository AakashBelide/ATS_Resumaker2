"use client";
// Landing "See it in action" console. A larger mac-window mock of the real platform that first
// auto-plays the whole workflow (onboard -> ingest -> discover -> track -> report -> dashboard ->
// mailer), then hands control to the visitor so they can actually click filters, track roles, open
// reports, onboard a company, and change digest settings. All mock, self-contained, no network.
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
  check: S(<path d="M20 6L9 17l-5-5" />),
  spark: S(<path d="M12 3l1.7 5.1L19 10l-5.3 1.9L12 17l-1.7-5.1L5 10l5.3-1.9L12 3z" />),
  back: S(<path d="M15 6l-6 6 6 6" />),
  doc: S(<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>),
  scan: S(<><path d="M4 8V5a1 1 0 0 1 1-1h3M20 8V5a1 1 0 0 0-1-1h-3M4 16v3a1 1 0 0 0 1 1h3M20 16v3a1 1 0 0 1-1 1h-3" /></>),
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
function buildReport(p: Posting): Report {
  return {
    subs: [
      { k: "skills", v: Math.min(95, p.fit + 12) },
      { k: "experience", v: Math.max(40, p.fit - 8) },
      { k: "domain", v: Math.min(92, p.fit + 6) },
      { k: "sponsorship", v: p.company === "Ramp" ? 30 : 80 },
    ],
    haves: [
      "Python, FastAPI, production LLM services",
      "RAG and retrieval evaluation, shipped to users",
      "GCP, Cloud Run, Airflow, event-driven pipelines",
    ],
    gaps: [
      "Kubernetes at scale (posting asks, profile is light)",
      `5+ yrs requested, you have 3 (fit adjusted, not hidden)`,
    ],
    skills: ["Python", "FastAPI", "RAG", "LangGraph", "GCP", "Airflow", "Prompt Eng", "Evals"],
    jd: `${p.company} is hiring a ${p.role} to build LLM-backed features end to end: retrieval, evaluation, and reliable serving. You will own data pipelines and ship to production with a small team.`,
    resume: [
      "Built a retrieval-augmented assistant on FastAPI + GCP serving 40k monthly queries at p95 under 900ms.",
      "Cut hallucinated answers 38% with a grounded-citation eval harness gating every release.",
      "Owned Airflow ingestion for 7 sources, dedupe and backfill, 99.9% freshness.",
    ],
    cover: `I am applying for the ${p.role} role at ${p.company}. My work centers on grounded LLM systems: retrieval, evaluation, and dependable serving, exactly the loop your posting describes. Every claim here traces to work I actually shipped.`,
    sponsor: p.company === "Ramp" ? "No sponsorship signalled, flagged before you spend effort" : "Sponsors H-1B, 14 approvals in USCIS history",
  };
}

type Tracked = {
  key: string; company: string; role: string; lvl: Lvl; fit: number;
  stage: string; loading: boolean; report: Report;
};
const seedTracked = (): Tracked[] => [
  { key: "ms", company: "Morgan Stanley", role: "AI Engineer", lvl: "mid", fit: 69, stage: "applied", loading: false, report: buildReport({ id: "ms", company: "Morgan Stanley", role: "AI Engineer", lvl: "mid", age: 2, fit: 69 }) },
  { key: "ramp0", company: "Ramp", role: "ML Engineer", lvl: "mid", fit: 58, stage: "interview", loading: false, report: buildReport(POSTINGS[1]) },
];
const seedBoards = () => [
  { name: "Stripe", on: true }, { name: "Anthropic", on: true }, { name: "Ramp", on: false },
];

const DAILY = [8, 12, 6, 15, 11, 9, 14]; // dashboard bar chart
const DOW = ["M", "T", "W", "T", "F", "S", "S"];

const TABS = [
  { key: "discovery", label: "Discovery", icon: ic.discovery },
  { key: "tracker", label: "Tracker", icon: ic.tracker },
  { key: "onboard", label: "Onboarding", icon: ic.onboard },
  { key: "dashboard", label: "Dashboard", icon: ic.dashboard },
  { key: "mailer", label: "Mailer", icon: ic.mailer },
];

/* ---- component ------------------------------------------------------------- */
export default function DemoConsole() {
  const [tab, setTab] = useState(0);
  const [auto, setAuto] = useState(true);
  const [pressed, setPressed] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [report, setReport] = useState<Tracked | null>(null);

  // discovery filters
  const [levels, setLevels] = useState<Record<Lvl, boolean>>({ junior: true, mid: true, senior: false });
  const [days, setDays] = useState(1);
  // tracker / boards / onboard / mailer
  const [tracked, setTracked] = useState<Tracked[]>(seedTracked);
  const [boards, setBoards] = useState(seedBoards);
  const [onbText, setOnbText] = useState("");
  const [onbStatus, setOnbStatus] = useState<"idle" | "resolving" | "done">("idle");
  const [onbSteps, setOnbSteps] = useState<string[]>([]);
  const [freq, setFreq] = useState<"daily" | "weekly" | "off">("daily");
  const [minFit, setMinFit] = useState(60);

  const timers = useRef<number[]>([]);
  const stopped = useRef(false);
  const started = useRef(false);
  const reportScroll = useRef<HTMLDivElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const wait = (ms: number) => new Promise<void>((res) => { const id = window.setTimeout(res, ms); timers.current.push(id); });

  const visible = POSTINGS.filter((p) => levels[p.lvl] && p.age <= days);

  /* --- shared actions (used by both autoplay and the visitor) --- */
  function trackPosting(p: Posting) {
    setTracked((prev) => {
      if (prev.some((t) => t.key === p.id)) return prev;
      return [...prev, { key: p.id, company: p.company, role: p.role, lvl: p.lvl, fit: p.fit, stage: "interested", loading: true, report: buildReport(p) }];
    });
    setTab(1);
    const id = window.setTimeout(() => setTracked((prev) => prev.map((t) => (t.key === p.id ? { ...t, loading: false } : t))), 1400);
    timers.current.push(id);
  }

  function takeControl() {
    if (!auto) return;
    stopped.current = true;
    clearTimers();
    setAuto(false);
    setIngesting(false);
    setPressed("");
    setTracked((prev) => prev.map((t) => ({ ...t, loading: false })));
  }

  /* --- autoplay tour --- */
  async function runTour() {
    stopped.current = false;
    clearTimers();
    // fresh slate
    setAuto(true); setReport(null); setIngesting(false); setPressed("");
    setLevels({ junior: true, mid: true, senior: false }); setDays(1);
    setTracked(seedTracked()); setBoards(seedBoards());
    setOnbText(""); setOnbStatus("idle"); setOnbSteps([]);
    setFreq("daily"); setMinFit(60);
    const dead = () => stopped.current;

    setTab(2); await wait(650); if (dead()) return;
    const name = "Databricks";
    for (let i = 1; i <= name.length; i++) { setOnbText(name.slice(0, i)); await wait(65); if (dead()) return; }
    await wait(350);
    setPressed("onb-go"); await wait(200); setPressed("");
    setOnbStatus("resolving");
    for (const st of ["Reading the careers page", "Found board at greenhouse.io/databricks", "Confirmed roles are live, adding to watchlist"]) {
      setOnbSteps((p) => [...p, st]); await wait(820); if (dead()) return;
    }
    setOnbStatus("done");
    setBoards((p) => (p.some((b) => b.name === "Databricks") ? p : [...p, { name: "Databricks", on: true }]));
    await wait(1100); if (dead()) return;

    setTab(0); setIngesting(true); await wait(1300); if (dead()) return;
    setIngesting(false); await wait(650); if (dead()) return;
    setPressed("days-7"); await wait(200); setPressed(""); setDays(7); await wait(1100); if (dead()) return;

    setPressed("track-databricks"); await wait(260); setPressed("");
    trackPosting(POSTINGS[0]); await wait(1900); if (dead()) return;

    const dbTracked = { key: "databricks" } as Tracked;
    setPressed("report-databricks"); await wait(220); setPressed("");
    setTracked((prev) => { const found = prev.find((t) => t.key === "databricks"); if (found) setReport(found); return prev; });
    void dbTracked;
    await wait(650); autoScrollReport(); await wait(3000); if (dead()) return;
    setReport(null); await wait(500); if (dead()) return;

    setTab(3); await wait(2400); if (dead()) return;
    setTab(4); await wait(800);
    setPressed("freq-weekly"); await wait(220); setPressed(""); setFreq("weekly"); await wait(1600); if (dead()) return;

    setTab(0); setAuto(false);
  }

  function autoScrollReport() {
    const el = reportScroll.current; if (!el) return;
    const max = el.scrollHeight - el.clientHeight; if (max <= 0) return;
    let y = 0;
    const step = () => {
      if (stopped.current || !reportScroll.current) return;
      y = Math.min(y + max / 44, max); el.scrollTop = y;
      if (y < max) { const id = window.setTimeout(step, 45); timers.current.push(id); }
    };
    step();
  }

  // start the tour once the console scrolls into view
  useEffect(() => {
    const node = rootRef.current; if (!node) return;
    const obs = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !started.current) { started.current = true; runTour(); }
    }, { threshold: 0.35 });
    obs.observe(node);
    return () => { obs.disconnect(); stopped.current = true; clearTimers(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* --- visitor onboarding (real interaction, mirrors the tour) --- */
  async function onboardNow() {
    const name = onbText.trim(); if (!name || onbStatus === "resolving") return;
    setOnbStatus("resolving"); setOnbSteps([]);
    for (const st of ["Reading the careers page", `Resolved ATS board for ${name}`, "Roles are live, added to watchlist"]) {
      setOnbSteps((p) => [...p, st]); await wait(700);
    }
    setOnbStatus("done");
    setBoards((p) => (p.some((b) => b.name.toLowerCase() === name.toLowerCase()) ? p : [...p, { name, on: true }]));
  }

  const goTab = (i: number) => { takeControl(); setReport(null); setTab(i); };

  return (
    <div className="dc" ref={rootRef}>
      {/* mac window chrome */}
      <div className="dc-bar">
        <span className="dc-dot r" /><span className="dc-dot y" /><span className="dc-dot g" />
        <em className="mono">ats-resumaker</em>
        <div className="dc-bar-right">
          {auto
            ? <button className="dc-tourbadge" onClick={takeControl}><span className="dc-live" />Auto tour playing, click to take control</button>
            : <button className="dc-replay" onClick={runTour}>{ic.spark}Replay tour</button>}
        </div>
      </div>

      <div className="dc-body">
        {/* left nav */}
        <nav className="dc-nav">
          {TABS.map((t, i) => (
            <button key={t.key} className={`dc-navitem ${tab === i ? "on" : ""}`} onClick={() => goTab(i)}>
              <span className="ico">{t.icon}</span><span>{t.label}</span>
            </button>
          ))}
          <div className="dc-nav-foot">
            <span className="dc-nav-user"><span className="dc-avatar" />Aakash</span>
          </div>
        </nav>

        {/* main */}
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
                  <Discovery
                    visible={visible} levels={levels} days={days} ingesting={ingesting} pressed={pressed}
                    onLevel={(l) => { takeControl(); setLevels((p) => ({ ...p, [l]: !p[l] })); }}
                    onDays={(d) => { takeControl(); setDays(d); }}
                    onTrack={(p) => { takeControl(); trackPosting(p); }}
                  />
                )}
                {tab === 1 && (
                  <TrackerView tracked={tracked} pressed={pressed}
                    onReport={(t) => { takeControl(); setReport(t); }} />
                )}
                {tab === 2 && (
                  <OnboardView text={onbText} status={onbStatus} steps={onbSteps} boards={boards} pressed={pressed}
                    onText={(v) => { takeControl(); setOnbText(v); }}
                    onGo={() => { takeControl(); onboardNow(); }}
                    onToggle={(n) => { takeControl(); setBoards((p) => p.map((b) => (b.name === n ? { ...b, on: !b.on } : b))); }} />
                )}
                {tab === 3 && <DashboardView tracked={tracked} boards={boards} />}
                {tab === 4 && (
                  <MailerView freq={freq} minFit={minFit} tracked={tracked} pressed={pressed}
                    onFreq={(f) => { takeControl(); setFreq(f); }}
                    onMinFit={(v) => { takeControl(); setMinFit(v); }} />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

/* ---- panels ---------------------------------------------------------------- */
function Discovery({ visible, levels, days, ingesting, pressed, onLevel, onDays, onTrack }: {
  visible: Posting[]; levels: Record<Lvl, boolean>; days: number; ingesting: boolean; pressed: string;
  onLevel: (l: Lvl) => void; onDays: (d: number) => void; onTrack: (p: Posting) => void;
}) {
  return (
    <div className="dc-pane">
      <div className="dc-pane-head">
        <h4>Discovery</h4><span className="dc-count">{visible.length} roles</span>
      </div>
      <div className="dc-filters">
        <span className="dc-fgrp">
          {(["junior", "mid", "senior"] as Lvl[]).map((l) => (
            <button key={l} className={`dc-pill ${levels[l] ? "on" : ""}`} onClick={() => onLevel(l)}>{l}</button>
          ))}
        </span>
        <span className="dc-fgrp">
          {[1, 7, 30].map((d) => (
            <button key={d} className={`dc-pill ${days === d ? "on" : ""} ${pressed === `days-${d}` ? "press" : ""}`} onClick={() => onDays(d)}>
              {d}d
            </button>
          ))}
        </span>
      </div>
      {ingesting && (
        <div className="dc-ingest"><span className="dc-live" />Hourly ingest running, polling onboarded boards</div>
      )}
      <div className="dc-jobs">
        <AnimatePresence>
          {visible.map((p, i) => (
            <motion.div key={p.id} layout className="dc-job"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
              transition={{ delay: ingesting ? 0 : i * 0.04, duration: 0.28 }}>
              <span className="dc-logo" />
              <div className="dc-job-txt">
                <span className="dc-job-t">{p.company} <i>{p.role}</i></span>
                <span className="dc-job-meta">{p.lvl} · {p.age}d ago · onboarded board</span>
              </div>
              <button className={`dc-track ${pressed === `track-${p.id}` ? "press" : ""}`} onClick={() => onTrack(p)}>+ Track</button>
            </motion.div>
          ))}
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
          <span className="c">
            {t.loading ? <span className="dc-shimmer" /> : <b className={`dc-fit ${t.fit >= 65 ? "hi" : t.fit >= 50 ? "mid" : "lo"}`}>{t.fit}</b>}
          </span>
          <span>{t.loading ? <span className="dc-shimmer wide" /> : <span className="dc-stage">{t.stage}</span>}</span>
          <span className="r">
            <button className={`dc-linkbtn ${pressed === `report-${t.key}` ? "press" : ""}`} disabled={t.loading} onClick={() => onReport(t)}>Report</button>
          </span>
        </div>
      ))}
      {tracked.some((t) => t.loading) && <div className="dc-matching"><span className="dc-live" />Matching against your profile, scoring fit and gaps</div>}
    </div>
  );
}

function ReportView({ t, onBack }: { t: Tracked; onBack: () => void }) {
  const r = t.report;
  return (
    <div className="dc-report">
      <button className="dc-back" onClick={onBack}>{ic.back}Back to tracker</button>
      <div className="dc-rep-head">
        <div>
          <div className="dc-rep-co">{t.company} <i>{t.role}</i></div>
          <div className="dc-rep-sub">{r.sponsor}</div>
        </div>
        <div className={`dc-rep-score ${t.fit >= 65 ? "hi" : "mid"}`}><b>{t.fit}</b><small>/100</small></div>
      </div>

      <div className="dc-rep-meters">
        {r.subs.map((s) => (
          <div className="dc-meter" key={s.k}>
            <span className="dc-meter-l">{s.k}</span>
            <span className="dc-meter-t"><motion.span className="dc-meter-f" initial={{ width: 0 }} animate={{ width: `${s.v}%` }} transition={{ duration: 0.7 }} /></span>
            <span className="dc-meter-v">{s.v}</span>
          </div>
        ))}
      </div>

      <div className="dc-rep-cols">
        <div className="dc-rep-card ok"><h5>{ic.check} You have</h5><ul>{r.haves.map((h) => <li key={h}>{h}</li>)}</ul></div>
        <div className="dc-rep-card gap"><h5>Gaps to address</h5><ul>{r.gaps.map((g) => <li key={g}>{g}</li>)}</ul></div>
      </div>

      <div className="dc-rep-chips">{r.skills.map((s) => <span key={s}>{s}</span>)}</div>

      <div className="dc-rep-block"><h5>{ic.doc} Job description</h5><p>{r.jd}</p></div>

      <div className="dc-rep-block"><h5>{ic.doc} Tailored resume, grounded to your profile</h5>
        <ul className="dc-bullets">{r.resume.map((b) => <li key={b}>{b}</li>)}</ul>
        <div className="dc-rep-actions"><button className="dc-linkbtn">Download PDF</button><button className="dc-linkbtn">Download DOCX</button></div>
      </div>

      <div className="dc-rep-block"><h5>{ic.mailer} Cover letter</h5><p>{r.cover}</p>
        <div className="dc-rep-actions"><button className="dc-linkbtn">Copy</button></div>
      </div>

      <div className="dc-rep-block"><h5>{ic.scan} Captured page screenshot</h5>
        <div className="dc-shot">
          <div className="dc-shot-bar"><span /><span /><span /></div>
          <div className="dc-shot-body">{Array.from({ length: 7 }).map((_, i) => <span key={i} className="dc-shot-line" style={{ width: `${90 - (i % 3) * 18}%` }} />)}</div>
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
      <div className="dc-pane-head"><h4>Onboarding</h4><span className="dc-count">agentic, $0 extra</span></div>
      <div className="dc-onb-form">
        <input className="dc-input" placeholder="Company name, e.g. Databricks" value={text}
          onChange={(e) => onText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onGo()} />
        <button className={`dc-btn ${pressed === "onb-go" ? "press" : ""}`} onClick={onGo} disabled={status === "resolving"}>
          {status === "resolving" ? "Resolving." : "Onboard"}
        </button>
      </div>
      <div className="dc-agent">
        <div className="dc-agent-head">{ic.spark}<span>Claude CLI is resolving the ATS board</span></div>
        <div className="dc-agent-steps">
          {steps.map((st, i) => (
            <motion.div key={i} className="dc-agent-step" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}>
              <span className="dc-agent-ok">{ic.check}</span>{st}
            </motion.div>
          ))}
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
          <div className="dc-kpi" key={l}><b>{n}</b><span>{l}</span></div>
        ))}
      </div>
      <div className="dc-chart-card">
        <div className="dc-chart-h">New postings per day</div>
        <div className="dc-chart">
          {DAILY.map((v, i) => (
            <div className="dc-bar-col" key={i}>
              <motion.span className="dc-bar" initial={{ height: 0 }} animate={{ height: `${(v / max) * 100}%` }} transition={{ delay: i * 0.05, duration: 0.5 }} />
              <em>{DOW[i]}</em>
            </div>
          ))}
        </div>
      </div>
      <div className="dc-toplist">
        <div className="dc-chart-h">Most active boards</div>
        {[["Databricks", 14], ["Stripe", 11], ["Anthropic", 9]].map(([n, c]) => (
          <div className="dc-toprow" key={n as string}><span className="dc-logo sm" /><span>{n}</span><b>{c} roles</b></div>
        ))}
      </div>
    </div>
  );
}

function MailerView({ freq, minFit, tracked, pressed, onFreq, onMinFit }: {
  freq: "daily" | "weekly" | "off"; minFit: number; tracked: Tracked[]; pressed: string;
  onFreq: (f: "daily" | "weekly" | "off") => void; onMinFit: (v: number) => void;
}) {
  const matches = tracked.filter((t) => !t.loading && t.fit >= minFit);
  return (
    <div className="dc-pane">
      <div className="dc-pane-head"><h4>Email digest</h4><span className="dc-count">delivered to you</span></div>
      <div className="dc-field"><label>Frequency</label>
        <div className="dc-seg">
          {(["daily", "weekly", "off"] as const).map((f) => (
            <button key={f} className={`${freq === f ? "on" : ""} ${pressed === `freq-${f}` ? "press" : ""}`} onClick={() => onFreq(f)}>{f}</button>
          ))}
        </div>
      </div>
      <div className="dc-field"><label>Only roles above fit {minFit}</label>
        <input type="range" min={0} max={90} step={5} value={minFit} className="dc-range" onChange={(e) => onMinFit(Number(e.target.value))} />
      </div>
      <div className="dc-mail-prev">
        <div className="dc-mail-top"><span className="dc-logo sm" /><b>ATS Resumaker</b><em>{freq === "off" ? "paused" : `${freq} digest`}</em></div>
        <div className="dc-mail-sub">{matches.length} roles above fit {minFit}, newest first</div>
        {matches.slice(0, 3).map((t) => (
          <div className="dc-mail-row" key={t.key}><span>{t.company} <i>{t.role}</i></span><b className={t.fit >= 65 ? "hi" : "mid"}>{t.fit}</b></div>
        ))}
        {freq === "off" && <div className="dc-mail-off">Digest paused, turn on daily or weekly to resume.</div>}
      </div>
    </div>
  );
}
