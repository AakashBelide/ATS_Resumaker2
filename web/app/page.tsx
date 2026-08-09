"use client";
// Minimal dashboard scaffold: start a run from a JD URL, watch live progress (SSE), and
// list past runs with their fit/ATS/gate outcomes + artifact links. Intentionally lean -
// the full review/approve UI is built in the frontend pass; this proves the API contract.
import { useEffect, useState } from "react";
import { artifactUrl, listRuns, startRun, subscribe, type RunRecord } from "@/lib/api";

export default function Dashboard() {
  const [url, setUrl] = useState("");
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [live, setLive] = useState<string>("");
  const [error, setError] = useState<string>("");

  async function refresh() {
    try { setRuns(await listRuns()); } catch (e) { setError(String(e)); }
  }
  useEffect(() => { refresh(); }, []);

  async function onStart() {
    setError(""); setLive("starting...");
    try {
      const { run_id } = await startRun(url);
      subscribe(run_id, (stage, status) => setLive(`${stage}: ${status}`));
    } catch (e) { setError(String(e)); }
  }

  return (
    <div>
      <h1>resumaker</h1>
      <p style={{ opacity: 0.7 }}>Paste a job-description URL to tailor a grounded, ATS-optimized resume.</p>
      <div style={{ display: "flex", gap: 8, margin: "1rem 0" }}>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://boards.greenhouse.io/.../jobs/123"
               style={{ flex: 1, padding: 8, borderRadius: 6, border: "1px solid #333", background: "#11141b", color: "#e6e8ee" }} />
        <button onClick={onStart} style={{ padding: "8px 16px", borderRadius: 6, background: "#3b82f6", color: "#fff", border: 0 }}>Tailor</button>
      </div>
      {live && <p style={{ color: "#facc15" }}>{live}</p>}
      {error && <p style={{ color: "#f87171" }}>{error}</p>}

      <h2 style={{ marginTop: "2rem" }}>Runs</h2>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead><tr style={{ textAlign: "left", opacity: 0.6 }}>
          <th>role</th><th>apply</th><th>fit</th><th>ATS</th><th>gate</th><th>pages</th><th>artifacts</th>
        </tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} style={{ borderTop: "1px solid #222" }}>
              <td>{r.url.split("/").slice(-1)[0] || r.id}</td>
              <td>{r.recommend_apply === null ? "-" : r.recommend_apply ? "yes" : "no"}</td>
              <td>{r.fit_0_100 ?? "-"}</td>
              <td>{r.ats_overall ?? "-"}</td>
              <td>{r.fact_gate_pass && r.ats_verify_pass ? "pass" : "-"}</td>
              <td>{r.page_count ?? "-"}</td>
              <td>
                <a href={artifactUrl(r.id, "resume.pdf")} style={{ color: "#60a5fa" }}>pdf</a>{" · "}
                <a href={artifactUrl(r.id, "cover_letter.txt")} style={{ color: "#60a5fa" }}>cover</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
