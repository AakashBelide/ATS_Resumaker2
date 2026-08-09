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
};

export async function listRuns(limit = 50): Promise<RunRecord[]> {
  const r = await fetch(`${BASE}/v1/runs?limit=${limit}`, { headers: headers() });
  if (!r.ok) throw new Error(`listRuns ${r.status}`);
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
