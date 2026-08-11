# Deployment & hosting — $0, reliable, resilient

Where each part of ATS Resumaker runs, why, the capacity math, and the alternatives — so the
hosting decision (and its trade-offs) isn't lost. Goal: **$0, but reliable and resilient**, with
no single free tier being load-bearing.

> **Decision (2026-08-11): go serverless on Cloud Run.** Oracle Always Free ARM (A1) was
> unobtainable — chronic "Out of host capacity" across all ADs, plus a VCN-count limit from the
> retries. Rather than fight capacity roulette, the chosen path removes the always-on VM entirely.
> Full plan in **[§ Chosen path: Serverless (Cloud Run)](#chosen-path-serverless-cloud-run)** below;
> the VM options remain as fallbacks.

## Chosen path: Serverless (Cloud Run)

Chosen deliberately as a **hobby/learning** build (wire up several managed GCP pieces), and because
it removes the always-on VM entirely — Google spins the container on demand and scales to zero.

### ⚠️ Use Cloud Run *services* (request-based), NOT Jobs or functions
The Always Free tier (2M req / **180k vCPU-s** / **360k GiB-s**) covers **request-based Cloud Run
services** only.
- **Cloud Run *Jobs*** bill *instance-based* → **NOT** covered by that free tier (would bill). Avoid.
- **Cloud Run *functions*** is a *different product* (rebranded Cloud Functions; 2M invocations /
  200k **GHz**-s) → wrong tool for our containers. Avoid.
- So **all batch work runs as request-based services** hit over HTTP (by Cloud Scheduler / Cloud Tasks).
  A "service" is just a container that runs when hit — it doesn't have to be a web app.

### Components
| Part | Runs on | Notes |
|---|---|---|
| **`api` service** (FastAPI, lean image) | Cloud Run service | read/query endpoints + triggers; ~1% of free tier |
| **`worker` service** (heavy image: LibreOffice, curl_cffi, …) | Cloud Run service | `POST /ingest-tick`, `POST /run-pipeline`; scale-to-zero, request-based |
| **DB** (SQLite) | **Turso** (libSQL, SQLite-compatible) | main code change; Cloud Run has no persistent disk |
| **Scheduler** | **Cloud Scheduler** (cron) → `POST /ingest-tick` | free: 3 jobs |
| **Async queue** (résumé) | **Cloud Tasks** → `POST /run-pipeline` | managed **work queue** (SQS/Celery-style, NOT Kafka; GCP's Kafka = Pub/Sub). Retries, rate-limit, delay. Free 1M ops/mo |
| **Onboarding sandbox** | **GitHub Actions** | needs Docker/root — Cloud Run can't nest it |
| **Artifacts** (.docx/.pdf) | **GCS bucket** (free 5 GB) / R2 | ephemeral FS → upload + signed URLs |
| **Frontend** | **Vercel** | route handlers hide the API token |
| **Secrets** | **GCP Secret Manager** / env | Turso, Resend, Anthropic, API token, GitHub PAT |

```
Browser ─▶ Vercel ─▶ Cloud Run `api` service ─▶ Turso (libSQL)
                          │                        ▲
Cloud Scheduler ─(every 2h, 8AM–10PM ET)─▶ `worker` /ingest-tick ─┘  + Resend email
"generate résumé" ─▶ api ─▶ Cloud Tasks ─▶ `worker` /run-pipeline (LibreOffice+LLM)
                                              └─ artifact ▶ GCS, status ▶ Turso
"onboard company" ─▶ api ─▶ GitHub Actions (Docker sandbox) ─▶ result ▶ api; new adapter ▶ PR
Frontend POLLS /v1/runs/{id} for progress   # replaces SSE
```

### Ingestion schedule (owner: 2-hourly, overnight pause, ET)
Cloud Scheduler cron **`0 8-22/2 * * *`**, timezone **`America/New_York`** (auto EST/EDT) → ~8
runs/day, **paused 10 PM–8 AM**; the 8 AM run catches everything overnight.
- **No dedup risk**: ingestion is idempotent — identity `(source, external_id)` + `content_hash`,
  only new/changed rows are inserted regardless of the time window (re-ingest 819 → 0 new, verified).
- **Bonus**: no 3 AM emails — the mailer batches overnight postings into one morning digest.

### Usage vs free tier (owner's max estimates)
- **Ingestion**: ~240 runs/mo × ~90 s = **~22k vCPU-s (12%)** of 180k.
- **Résumé-gen**: 300/mo × ~3 min = **~54k vCPU-s (30%)**.
- **API**: ~2k vCPU-s (~1%).
- **Cloud Run total ≈ 78k of 180k vCPU-s (43%), ~173k of 360k GiB-s (48%)** → comfortably free.
- **Onboarding**: GitHub Actions, 200/mo × ~4 min (**prebuilt image**) = **~800 of 2,000 min (40%)**.
- **Prebuilt images are mandatory** — building per-run (LibreOffice/Playwright/Node ≈ 5–8 min) blows
  every budget. Build once on push → `docker pull` (~1 min) at run time.

### Setup order
Turso DB → GCS bucket → build a lean **api** image + a heavier **worker** image (prebuilt, pushed to
Artifact Registry — the small api image fits the 0.5 GB free; the worker image ~cents) → deploy both
as Cloud Run services (`--min-instances=0`) → Cloud Scheduler cron → Cloud Tasks queue → GitHub
Actions workflow for onboarding → Vercel frontend pointed at the api URL.

### Prebuilt images — what / where / cost
Build once on code-change, store, and **pull at runtime** (~1 min) — never build per run.

| Image | Contains | Used by | Stored in | ~size |
|---|---|---|---|---|
| `api` | FastAPI + core + Turso client (no LibreOffice/Playwright/Node) | Cloud Run `api` | **Artifact Registry** | ~250 MB |
| `worker` | + LibreOffice + curl_cffi (+ Playwright only if needed) + LLM client | Cloud Run `worker` | **Artifact Registry** | ~400–700 MB |
| `onboard-agent` | Node + Claude CLI + resolver tools (`onboard-agent:poc`) | GitHub Actions sandbox | **ghcr.io** | ~300 MB |
| `onboard-proxy` | tiny egress proxy | GitHub Actions sandbox | **ghcr.io** | ~30 MB |

**Cost:** pulls are free (same-region Cloud Run↔Artifact Registry; Actions↔ghcr); builds are free
(Cloud Build 120 min/day or an Actions build job). Storage: Artifact Registry free = 0.5 GB → `api`+
`worker` slightly over → **~a few cents/month (accepted)**; ghcr private free = 500 MB → onboarding
images fit. **Set a "keep latest 1–2 versions" cleanup policy** so old pushes don't accumulate past
the free tiers.

### Code changes (the refactor)
1. **DB layer** — `persistence/db.py` `connect()` → libSQL/Turso (SQL unchanged; sync `libsql` client
   ≈ `sqlite3` — exercise the repository methods). *Biggest task.*
2. **Drop in-process APScheduler** → a `worker` endpoint `POST /ingest-tick` running one tick; Cloud Scheduler calls it.
3. **Pipeline off the request thread** → `worker` endpoint `POST /run-pipeline`; `api` enqueues via Cloud Tasks; status persists to `runs` (already does).
4. **SSE → polling** — frontend swaps `EventSource` for polling `/v1/runs/{id}`.
5. **Artifacts → bucket** — `outputs/` writes become GCS uploads + signed URLs.
6. **PDF on demand** — ship `.docx` by default; render PDF (LibreOffice) only when downloaded (keeps most runs light).
7. **Containerize for `$PORT`** (Dockerfile exists) — split into lean **api** + heavy **worker** images.

### Gotchas
- **LLM auth in the cloud**: the *subscription* `claude` CLI on a cloud host is ToS-gray — use the
  **metered Anthropic API** (`RESUMAKER_DEFAULT_PROVIDER=anthropic`) for cloud runs; cost is tiny.
  Keep the subscription CLI for local/dev.
- **Cold starts** ~1–3 s after idle; **no SSE** (poll the DB status); **no Docker sandbox on Cloud Run** (onboarding → Actions); **Turso** is mostly drop-in but test the DB layer.
- $0 when idle; all within free tiers at the owner's estimates.

### Reality check
This is **8 moving parts** (api + worker services + Scheduler + Cloud Tasks + Turso + GCS + Vercel +
Actions) — great for learning, more to build/debug. A **$5 VPS** collapses all of it into one warm box
(no cold starts, no per-run image pulls, résumés generate instantly). Same Docker Compose either way,
so serverless-now → VPS-later (or vice-versa) is a redeploy. Chosen: serverless, for the learning value.

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
