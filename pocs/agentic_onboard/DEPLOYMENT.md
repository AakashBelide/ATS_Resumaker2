# Deployment & hosting — $0, reliable, resilient

Where each part of ATS Resumaker runs, why, the capacity math, and the alternatives — so the
hosting decision (and its trade-offs) isn't lost. Goal: **$0, but reliable and resilient**, with
no single free tier being load-bearing.

## The workload has 4 distinct parts (host them where they fit)
1. **Always-on core** — FastAPI API + SQLite + APScheduler + ingestion + mailer. Light, must be up.
2. **Frontend** — Next.js. Static/SSR.
3. **Heavy occasional jobs** — onboarding sandbox, adapter-authoring, résumé-gen (LibreOffice + CLI). Rare, memory-hungry.
4. **The DB** — SQLite (a file; single-writer; fine for one user).

The trick: these do NOT have to share a machine.

## Recommended topology (the 3-way split)
```
Browser ──▶ Vercel (Next.js)                         # frontend on its home turf
                │ server-side route handlers proxy to the API (token stays server-side)
                ▼
GCP e2-micro ──▶ FastAPI + SQLite + scheduler + ingestion + mailer   # always-on core, HTTPS via Caddy
                │ triggers heavy jobs via GitHub REST API (workflow_dispatch)
                ▼
GitHub Actions ──▶ ephemeral 16 GB runner (Docker/bwrap sandbox)      # heavy occasional jobs
                • resolver/author agent (CLAUDE_CODE_OAUTH_TOKEN = Actions secret)
                • resolve result ──POST /v1/onboard/result──▶ backend (API token)
                • new adapter draft ──▶ opens a Pull Request (review = the gate + human merge)
```
`needs_input` across the boundary is stateless: the Action posts the question to the backend and
**exits**; the human answers in the UI → the backend **re-dispatches a fresh Action** with the answer.

## Capacity — does the core fit on GCP e2-micro (1 GB)?
Yes for the core; the trio is the light part.

| Component | RAM |
|---|---|
| uvicorn + FastAPI (workers=1) | ~120–200 MB |
| APScheduler (in-process) | a few MB |
| SQLite (WAL, single-user) | ~10–30 MB |
| Ingestion tick (77 boards, httpx/curl_cffi) | ~100–250 MB transient |

Steady state ≈ **250–400 MB of 1 GB** (~600 MB headroom). Caveats: CPU is **shared/bursty** (fine
for single-user I/O-bound work, sluggish under sustained load); network **egress** is metered
(~1 GB/mo free — fine for one user; downloads/ingress are free).

### The one real risk: a heavy job on the 1 GB box
LibreOffice (~350 MB) + `claude` CLI (~300 MB) + backend (~300 MB) ≈ **~1 GB peak** for one
résumé-gen. Never concurrent (single user), but still a spike. Fixes (any one):
- **Add a 2–4 GB swap file** — turns a potential OOM-kill into "a few seconds slower." Cheapest, do this regardless.
- **Cap concurrency = 1** for pipeline runs (already the ThreadPoolExecutor pattern) + a cgroup `MemoryMax` on the job so it can never take the box down.
- **Offload résumé-gen to Actions** too (bulletproof — the VM never spikes). Onboarding/adapter-authoring already go there.

## Alternatives ($0, ranked by reliability-per-effort)

| Topology | $0 | Resilience | Effort | Heavy-job RAM risk |
|---|---|---|---|---|
| **A. Oracle Always Free ARM (24 GB) + Vercel** | ✅ | single-provider | **low** | **none** (24 GB fits everything incl. sandboxes) |
| **B. GCP e2-micro split** (core on GCP · jobs on Actions · UI on Vercel) | ✅ | multi-provider | med–high | mitigated (swap / offload) |
| **C. Serverless-core** (Cloud Run + Turso + cron + Vercel + Actions) | ✅ (idle) | **high** (managed, scale-to-zero) | high (DB swap) | none (no always-on VM) |
| **D. $5 VPS** (Hetzner CX22, 4 GB) all-in-one | ❌ ($5/mo) | single box | **low** | none |
| **E. Self-host** (old laptop/Pi + Cloudflare Tunnel) | ✅ | low (home power/net) | med | HW-dependent |

### A — Oracle Always Free ARM (24 GB)
The simplest and most headroom: one box runs the core **and** the sandboxes **and** résumé-gen,
no tightness. Only downside = single-provider risk (the "what if Oracle pulls it" worry). Mitigated
by keeping everything portable (just Docker + bwrap) so moving is a redeploy, not a rewrite.

### B — GCP e2-micro split (this doc's recommended topology)
$0 and provider-resilient (lose any one, swap it independently), at the cost of more glue (CORS,
TLS, three tokens, async orchestration) and the 1 GB tightness handled above.

### C — Serverless-core (the most resilient $0 option)
Remove the always-on VM entirely: **Cloud Run** (FastAPI container, scales to zero — $0 when idle,
2M req/mo free) + a **hosted SQLite** (**Turso**/libSQL free tier — SQLite-compatible, ~drop-in) +
scheduling via **Cloud Scheduler** or a **cron GitHub Action** hitting an ingest endpoint + Vercel
+ Actions for heavy jobs. Nothing to OOM, nothing to preempt, managed uptime. Cost: a light
persistence-layer swap (`sqlite3` → libSQL client) and pushing LibreOffice off the request path
(→ Actions). Best "$0 + resilient" if willing to do the DB move.

### D — $5 VPS
Not $0, but the reliability floor: 4 GB runs *everything* on one box with none of the tightness or
glue. The pragmatic answer if the split's moving parts aren't worth it.

## Recommendation
- **Right now, if Oracle Always Free is available: take A** (24 GB, one box, everything fits) and
  keep it portable. Simplest reliable $0.
- **To not depend on Oracle: B** (GCP split) with **swap on** and résumé-gen offloaded to Actions —
  or **C** (serverless-core) if you want the most resilient, no-VM-to-babysit option and don't mind
  the SQLite→Turso swap.
- **If $0 stops being worth the glue: D** ($5 VPS) ends the whole discussion.

Non-negotiables on any 1 GB box: **swap file (2–4 GB)**, uvicorn `workers=1`, frontend on Vercel
(no Node RAM on the VM), and heavy jobs (sandbox + LibreOffice) off the box or strictly serialized.
