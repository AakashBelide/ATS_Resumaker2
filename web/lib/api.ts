// Typed client for the resumaker API. The dashboard talks only to this module so the API
// contract lives in one place. ALL calls go through the same-origin BFF proxy
// (web/app/api/[...path]/route.ts), which attaches the API token SERVER-SIDE — so the token is
// never shipped to the browser (and there's no CORS). The proxy's upstream + token come from the
// server-only env vars API_ORIGIN + API_TOKEN (set on Vercel / in web/.env.local for dev).
const BASE = "/api";

function headers(): HeadersInit {
  return { "Content-Type": "application/json" };  // auth is added by the proxy, not here
}

export type RunRecord = {
  id: string; url: string; status: string; out_dir: string;
  recommend_apply: boolean | null; fit_0_100: number | null;
  ats_overall: number | null; fact_gate_pass: boolean | null;
  ats_verify_pass: boolean | null; page_count: number | null;
  cost_usd: number; created_at: string | null; finished_at: string | null;
};

export async function listRuns(limit = 50): Promise<RunRecord[]> {
  const r = await fetch(`${BASE}/v1/runs?limit=${limit}`, { headers: headers() });
  if (!r.ok) throw new Error(`listRuns ${r.status}`);
  return r.json();
}

export async function getRun(runId: string): Promise<RunRecord> {
  const r = await fetch(`${BASE}/v1/runs/${encodeURIComponent(runId)}`, { headers: headers() });
  if (!r.ok) throw new Error(`getRun ${r.status}`);
  return r.json();
}

// `runId` (optional): when generating from a tracked job, pass that job's stable id so the
// tailored resume is written into its match-report folder (overwriting report.json with the
// resume-bearing version). The report page then shows the documents on reload - no id to remember.
export async function startRun(url: string, runId?: string): Promise<{ run_id: string }> {
  const r = await fetch(`${BASE}/v1/runs`, {
    method: "POST", headers: headers(),
    body: JSON.stringify(runId ? { url, run_id: runId } : { url }),
  });
  if (!r.ok) throw new Error(`startRun ${r.status}`);
  return r.json();
}

export type RunProgress = {
  current: string; done: boolean; elapsed: number;
  stages: { stage: string; status: string; detail: string; elapsed: number | null }[];
};
// Poll a run's progress snapshot (replaces SSE - a scale-to-zero backend can't hold a stream).
export async function getProgress(runId: string): Promise<RunProgress> {
  const r = await fetch(`${BASE}/v1/runs/${encodeURIComponent(runId)}/progress`, { headers: headers() });
  if (!r.ok) throw new Error(`getProgress ${r.status}`);
  return r.json();
}

export function artifactUrl(runId: string, name: string): string {
  return `${BASE}/v1/runs/${runId}/artifacts/${name}`;
}
// Force a direct download (Content-Disposition attachment, streamed through the proxy) instead of
// the inline/signed-URL view - used for the resume PDF/DOCX buttons so they save straight away.
export function artifactDownloadUrl(runId: string, name: string): string {
  return `${artifactUrl(runId, name)}?download=1`;
}
// Fetch a text artifact's contents (e.g. cover_letter.txt) to render inline. Goes through the
// same-origin proxy, which attaches the token, so no auth header is needed here.
export async function fetchArtifactText(runId: string, name: string): Promise<string> {
  const r = await fetch(artifactUrl(runId, name));
  if (!r.ok) throw new Error(`artifact ${name} → ${r.status}`);
  return r.text();
}

export async function costs(): Promise<Record<string, unknown>> {
  const r = await fetch(`${BASE}/v1/costs`, { headers: headers() });
  return r.json();
}

// ---- shared helpers (RA platform) -------------------------------------------
type QVal = string | number | boolean | string[] | undefined;
function qs(params: Record<string, QVal>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "") continue;
    if (Array.isArray(v)) { if (v.length) p.set(k, v.join(",")); }  // multi-select -> csv
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}
async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: headers() });
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

// ---- Discovery (RA.1) -------------------------------------------------------
export type JobRecord = {
  id: number | null; source: string; external_id: string; url: string; title: string;
  company: string; location: string; status: string; posted_at: string;
  comp: string; first_seen: string | null; last_seen: string | null;
};
export type DiscoveryFacets = {
  companies: Record<string, number>; sources: Record<string, number>;
  states: Record<string, number>; levels: Record<string, number>;
};
export type Discovery = { total: number; jobs: JobRecord[]; facets: DiscoveryFacets };
export type DiscoveryQuery = {
  company?: string[]; source?: string; location?: string; keyword?: string;
  title_include?: string[]; title_exclude?: string[];
  since_days?: number; on_target?: boolean; state?: string[]; level?: string[];
  order?: string; limit?: number; offset?: number;
};
export function discovery(q: DiscoveryQuery = {}): Promise<Discovery> {
  return get<Discovery>(`/v1/discovery${qs(q)}`);
}

// ---- Tracker (RA.2) ---------------------------------------------------------
export type TrackerEntry = {
  id: number | null; job_id: number | null; url: string; company: string; title: string;
  stage: string; run_id: string; fit_0_100: number | null; recommend_apply: boolean | null;
  sponsorship: string; match_error: string | null; location: string; salary: string;
  notes: string; created_at: string | null; updated_at: string | null;
};
export function listTracker(stage?: string): Promise<TrackerEntry[]> {
  return get<TrackerEntry[]>(`/v1/tracker${qs({ stage })}`);
}
// The tracked entry for a match run (authoritative ATS title/company), or null for an ad-hoc run.
export async function getTrackerByRun(runId: string): Promise<TrackerEntry | null> {
  const r = await fetch(`${BASE}/v1/tracker/by-run/${encodeURIComponent(runId)}`, { headers: headers() });
  return r.ok ? r.json() : null;
}
export async function rematchTracker(id: number): Promise<TrackerEntry> {
  const r = await fetch(`${BASE}/v1/tracker/${id}/rematch`, { method: "POST", headers: headers() });
  if (!r.ok) throw new Error(`rematchTracker → ${r.status}`);
  return r.json();
}
export async function deleteTracker(id: number): Promise<void> {
  const r = await fetch(`${BASE}/v1/tracker/${id}`, { method: "DELETE", headers: headers() });
  if (!r.ok) throw new Error(`deleteTracker → ${r.status}`);
}
export async function addTracker(body: { job_id?: number; url?: string; run_match?: boolean }): Promise<TrackerEntry> {
  const r = await fetch(`${BASE}/v1/tracker`, { method: "POST", headers: headers(), body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`addTracker → ${r.status}`);
  return r.json();
}
export async function setTrackerStage(id: number, stage: string): Promise<TrackerEntry> {
  const r = await fetch(`${BASE}/v1/tracker/${id}/stage`, {
    method: "PATCH", headers: headers(), body: JSON.stringify({ stage }),
  });
  if (!r.ok) throw new Error(`setTrackerStage → ${r.status}`);
  return r.json();
}

// ---- Profile (RA.3) ---------------------------------------------------------
export type ProfileSummary = {
  employers: string[]; titles: string[]; skills: string[]; n_metrics: number; n_skills: number;
  years_experience: number; needs_sponsorship: boolean; preferences: Record<string, unknown>;
};
export type Proposal = { requirement: string; count: number; companies: string[]; evidence: string };
export const profileSummary = () => get<ProfileSummary>("/v1/profile/summary");
export const profileProposals = () =>
  get<{ have_but_unlisted: Proposal[]; recurring_gaps: Proposal[] }>("/v1/profile/proposals");

export type Preferences = { target_roles: string[]; avoid_roles: string[] };
export const getPreferences = () => get<Preferences>("/v1/profile/preferences");
export async function savePreferences(p: Preferences): Promise<Preferences> {
  const r = await fetch(`${BASE}/v1/profile/preferences`, {
    method: "PUT", headers: headers(), body: JSON.stringify(p),
  });
  if (!r.ok) throw new Error(`savePreferences → ${r.status}`);
  return r.json();
}

export type MailerPrefs = {
  include: string[]; exclude: string[]; levels: string[]; states: string[];
  quiet_enabled: boolean; quiet_start: string; quiet_end: string;
  timezone: string; max_postings: number; frequency: string;
};
export const getMailerPrefs = () => get<MailerPrefs>("/v1/mailer/prefs");
export async function saveMailerPrefs(p: MailerPrefs): Promise<MailerPrefs> {
  const r = await fetch(`${BASE}/v1/mailer/prefs`, {
    method: "PUT", headers: headers(), body: JSON.stringify(p),
  });
  if (!r.ok) throw new Error(`saveMailerPrefs → ${r.status}`);
  return r.json();
}

export type MailerPreview = { on_target: number; matching: number; cap: number; would_send: number };
export async function previewMailer(p: MailerPrefs): Promise<MailerPreview> {
  const r = await fetch(`${BASE}/v1/mailer/preview`, {
    method: "POST", headers: headers(), body: JSON.stringify(p),
  });
  if (!r.ok) throw new Error(`previewMailer → ${r.status}`);
  return r.json();
}

export type MailerFilter = { include: string[]; exclude: string[] };
export const getMailerFilter = () => get<MailerFilter>("/v1/profile/mailer-filter");
export async function saveMailerFilter(mf: MailerFilter): Promise<MailerFilter> {
  const r = await fetch(`${BASE}/v1/profile/mailer-filter`, {
    method: "PUT", headers: headers(), body: JSON.stringify(mf),
  });
  if (!r.ok) throw new Error(`saveMailerFilter → ${r.status}`);
  return r.json();
}

// ---- Dashboard (RA.4) + Metrics (RA.5) --------------------------------------
export type Dashboard = {
  watchlist: { companies: number; jobs: number; tracked: number };
  jobs_by_company: Record<string, number>; jobs_by_source: Record<string, number>;
  new_listings_daily: { date: string; count: number }[];
  tracker_funnel: Record<string, number>;
  runs: { total: number; by_status: Record<string, number>; avg_fit: number | null; avg_ats: number | null; total_cost_usd: number };
};
export const dashboard = (days = 14) => get<Dashboard>(`/v1/dashboard${qs({ days })}`);
export const metrics = () => get<{ cost: Record<string, any>; runs: Dashboard["runs"] }>("/v1/metrics");

export async function setTrackerNotes(id: number, notes: string): Promise<TrackerEntry> {
  const r = await fetch(`${BASE}/v1/tracker/${id}/notes`, {
    method: "PATCH", headers: headers(), body: JSON.stringify({ notes }),
  });
  if (!r.ok) throw new Error(`setTrackerNotes → ${r.status}`);
  return r.json();
}

// ---- Match report (report.json served as a run artifact) --------------------
export type ReportJob = {
  title: string; company: string; location: string; work_model: string;
  remote_restriction: string; seniority: string; salary_range: string;
  work_auth_note: string; sponsorship_stance: string;
  required_quals: string[]; preferred_quals: string[]; responsibilities: string[];
  knockouts: { question: string; kind: string; hard: boolean }[];
  source_url: string; source_type: string; raw_text: string;
};
export type ReportGapItem = { requirement: string; status: string; evidence: string; substitution: string };
export type Report = {
  url: string; out_dir: string; gated_out: boolean;
  job: ReportJob;
  keyword_set: { keywords: { term: string; weight: number; kind: string }[]; standardized: string[] };
  gap: { items: ReportGapItem[]; gaps: string[]; substitutions: unknown[] };
  fit: {
    dimensions: Record<string, number>;
    deterministic_0_100: number; llm_0_100: number; final_0_100: number; final_1_5: number;
    rationale: string;
  };
  sponsorship: { verdict: string; hard_blocker: boolean; source: string; needs_verification: boolean; reasons: string[] };
  decision: { recommend_apply: boolean; confidence: string; reasons: string[]; blockers: string[] };
  // populated only by the FULL pipeline (null in a match-only run). `resume` carries `uploaded:true`
  // when the owner attached their own PDF instead of generating one (then there's no DOCX/ATS).
  resume: ({ uploaded?: boolean; filename?: string } & Record<string, unknown>) | null;
  cover_letter: unknown | null; ats: { overall?: number } | null;
  warnings: string[]; error: string | null;
};
// Attach an owner-supplied resume PDF to a run (stored in the bucket as resume.pdf; report.json is
// flagged so the report shows it). `dataUrl` is a base64 data: URL from FileReader.readAsDataURL.
export async function uploadResume(runId: string, dataUrl: string, filename: string): Promise<{ ok: boolean }> {
  const r = await fetch(`${BASE}/v1/runs/${encodeURIComponent(runId)}/resume-upload`, {
    method: "POST", headers: headers(),
    body: JSON.stringify({ pdf_base64: dataUrl, filename }),
  });
  if (!r.ok) throw new Error(`uploadResume → ${r.status}`);
  return r.json();
}
export async function getReport(runId: string): Promise<Report> {
  const r = await fetch(`${BASE}/v1/runs/${encodeURIComponent(runId)}/artifacts/report.json`, { headers: headers() });
  if (!r.ok) throw new Error(`getReport → ${r.status}`);
  return r.json();
}
// Like getReport but returns null when report.json isn't published yet (404) instead of throwing,
// so the report page can show a friendly "matching…" loading state and poll until it appears. Any
// OTHER failure (non-404) still throws, so genuine/persistent errors surface as a hard error box.
export async function getReportOrNull(runId: string): Promise<Report | null> {
  const r = await fetch(`${BASE}/v1/runs/${encodeURIComponent(runId)}/artifacts/report.json`, { headers: headers() });
  if (r.status === 404) return null;              // report not ready yet (match still running)
  if (!r.ok) throw new Error(`getReport → ${r.status}`);
  return r.json();
}

// ---- Onboarding (RI.0) ------------------------------------------------------
export type Company = { id: number | null; name: string; active: boolean; boards: { source: string; token: string; extra: Record<string, string> }[] };
export const listCompanies = () => get<Company[]>("/v1/companies");
export async function setCompanyActive(name: string, active: boolean): Promise<{ name: string; active: boolean }> {
  const r = await fetch(`${BASE}/v1/companies/${encodeURIComponent(name)}/active`, {
    method: "PATCH", headers: headers(), body: JSON.stringify({ active }),
  });
  if (!r.ok) throw new Error(`setCompanyActive → ${r.status}`);
  return r.json();
}

// Agentic onboarding (Phase C) — async, human-in-the-loop.
export type OnboardState = "running" | "needs_input" | "resolved" | "drafted" | "unresolved" | "killed" | "stopped" | "error";
export type OnboardEvent = { stage: string; status: string; detail: string; ts: number };
export type OnboardingRun = {
  id: string; name: string; careers_url: string; method: string; state: OnboardState;
  question: string; board: { source: string; token: string; extra: Record<string, string> } | null;
  evidence: Record<string, unknown>; events: OnboardEvent[]; cost_usd: number; turns: number;
  error: string; created_at: string | null; updated_at: string | null;
};
export async function startOnboard(name: string, careers_url?: string): Promise<OnboardingRun> {
  const r = await fetch(`${BASE}/v1/onboard`, {
    method: "POST", headers: headers(), body: JSON.stringify({ name, careers_url }),
  });
  if (!r.ok) throw new Error(`startOnboard → ${r.status}`);
  return r.json();
}
export const getOnboardRun = (id: string) => get<OnboardingRun>(`/v1/onboard/${encodeURIComponent(id)}`);
export const listOnboardRuns = (limit = 10) => get<OnboardingRun[]>(`/v1/onboard?limit=${limit}`);
export async function provideOnboardInput(id: string, answer: string): Promise<OnboardingRun> {
  const r = await fetch(`${BASE}/v1/onboard/${encodeURIComponent(id)}/input`, {
    method: "POST", headers: headers(), body: JSON.stringify({ answer }),
  });
  if (!r.ok) throw new Error(`provideOnboardInput → ${r.status}`);
  return r.json();
}
export async function stopOnboard(id: string): Promise<OnboardingRun> {
  const r = await fetch(`${BASE}/v1/onboard/${encodeURIComponent(id)}/stop`, { method: "POST", headers: headers() });
  if (!r.ok) throw new Error(`stopOnboard → ${r.status}`);
  return r.json();
}
