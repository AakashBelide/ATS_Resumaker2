// Typed client for the resumaker API. The dashboard talks only to this module so the
// API contract lives in one place. Config via NEXT_PUBLIC_API_BASE + NEXT_PUBLIC_API_TOKEN.

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

function headers(): HeadersInit {
  return TOKEN ? { "X-API-Key": TOKEN, "Content-Type": "application/json" }
               : { "Content-Type": "application/json" };
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

export async function startRun(url: string): Promise<{ run_id: string }> {
  const r = await fetch(`${BASE}/v1/runs`, {
    method: "POST", headers: headers(), body: JSON.stringify({ url }),
  });
  if (!r.ok) throw new Error(`startRun ${r.status}`);
  return r.json();
}

// Subscribe to a run's SSE progress stream. Returns an unsubscribe fn.
export function subscribe(runId: string, onEvent: (stage: string, status: string) => void): () => void {
  const es = new EventSource(`${BASE}/v1/runs/${runId}/events`);
  es.addEventListener("progress", (e) => {
    const [stage, status] = (e as MessageEvent).data.split(":");
    onEvent(stage, status);
  });
  es.addEventListener("end", () => es.close());
  return () => es.close();
}

export function artifactUrl(runId: string, name: string): string {
  return `${BASE}/v1/runs/${runId}/artifacts/${name}`;
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
  first_seen: string | null; last_seen: string | null;
};
export type DiscoveryFacets = {
  companies: Record<string, number>; sources: Record<string, number>;
  states: Record<string, number>; levels: Record<string, number>;
};
export type Discovery = { total: number; jobs: JobRecord[]; facets: DiscoveryFacets };
export type DiscoveryQuery = {
  company?: string[]; source?: string; location?: string; keyword?: string;
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
  sponsorship: string; notes: string; created_at: string | null; updated_at: string | null;
};
export function listTracker(stage?: string): Promise<TrackerEntry[]> {
  return get<TrackerEntry[]>(`/v1/tracker${qs({ stage })}`);
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
  // populated only by the FULL pipeline (null in a match-only run)
  resume: unknown | null; cover_letter: unknown | null; ats: { overall?: number } | null;
  warnings: string[]; error: string | null;
};
export async function getReport(runId: string): Promise<Report> {
  const r = await fetch(`${BASE}/v1/runs/${encodeURIComponent(runId)}/artifacts/report.json`, { headers: headers() });
  if (!r.ok) throw new Error(`getReport → ${r.status}`);
  return r.json();
}

// ---- Onboarding (RI.0) ------------------------------------------------------
export type Company = { id: number | null; name: string; active: boolean; boards: { source: string; token: string; extra: Record<string, string> }[] };
export type OnboardResult = { name: string; resolved: boolean; method: string; boards: { source: string; token: string; extra: Record<string, string> }[]; note: string; tried: string[] };
export const listCompanies = () => get<Company[]>("/v1/companies");
export async function setCompanyActive(name: string, active: boolean): Promise<{ name: string; active: boolean }> {
  const r = await fetch(`${BASE}/v1/companies/${encodeURIComponent(name)}/active`, {
    method: "PATCH", headers: headers(), body: JSON.stringify({ active }),
  });
  if (!r.ok) throw new Error(`setCompanyActive → ${r.status}`);
  return r.json();
}
export async function onboard(name: string, careers_url?: string, add = true): Promise<OnboardResult> {
  const r = await fetch(`${BASE}/v1/onboard`, {
    method: "POST", headers: headers(), body: JSON.stringify({ name, careers_url, add }),
  });
  if (!r.ok) throw new Error(`onboard → ${r.status}`);
  return r.json();
}
