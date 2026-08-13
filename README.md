# ATS Resumaker

Accuracy-first system that turns a job posting into a grounded, ATS-optimized
**resume + cover letter + apply/no-apply decision** — traced strictly to a canonical
source-of-truth profile, with a hard anti-fabrication gate. Around that pipeline is a
full **job-application platform**: a watchlist that auto-onboards companies and ingests
their postings, a browser extension that captures a posting in one click, and a web
dashboard to triage, match, and tailor. Human-in-the-loop: it advises and drafts; it
never auto-applies.

## What it does
**Per-posting pipeline:** `JD (URL or captured page) → scrape → structure → keywords · gap · sponsorship (parallel) → fit → apply-decision → resume (tailor · deterministic skills · docx→pdf · fact-gate · ATS-verify · ATS-score) → cover letter`.

**Application platform (built on top):**
- **Discovery** — a deterministic, LLM-free feed of ingested postings (filter by company / role / recency / location / level). No resume-fit ranking (validated: it misranks).
- **Tracker** — add a posting → runs the match (fit / gap / sponsorship / keywords) only; resume + cover are an on-demand manual trigger. Application lifecycle (interested → applied → interview → offer / rejected / skipped).
- **Onboarding** — give a company name (+ optional careers URL) → an agent resolves its ATS board; unresolved falls back to manual.
- **Profile · Dashboard · Metrics** — the signals the match uses, analytics over the watchlist/tracker, and per-provider LLM cost/usage.
- **Browser extension (MV3)** — a floating capture button grabs the posting text + a full-page screenshot and tracks it via the API.

## Architecture (modular monolith · single-user · dual-mode local/cloud)
```
src/resumaker/          # core library (pure domain logic, no web deps)
  config/  domain/  observability/  persistence/(files + SQLite/libSQL + cache)
  providers/  llm/(Claude CLI · Anthropic API · Gemini, registry + cache + fallback)
              scrape/(single JD)   sources/(board-listing adapters: 24 covering ~77 cos)
  stages/    scrape → structure → keywords · gap · sponsorship → fit → apply → tailor …
  ats/       scorer · semantic · verify · skills_rank · fact_gate · sim/
  pipeline/  orchestrator (stage DAG) + progress
  enrichment/  ingestion/(onboard · discovery · tracker · service · scheduler · notify)
apps/api/   FastAPI: runs · discovery · tracker · onboard · profile · mailer · dashboard
            · metrics · worker (Cloud Tasks/Scheduler targets); token auth
apps/cli/   run · watch · ingest · onboard · discovery · track · schedule · costs · serve
web/        Next.js dashboard (Discovery/Tracker/Onboarding/Profile/Mailer/Dashboard/Metrics)
extension/  MV3 capture extension (full-page screenshot + track)
deploy/     Dockerfile.api · Dockerfile.worker · compose · Caddy · terraform/ (Cloud Run)
```
Right-sized on purpose: **no microservices, no Redis, no Postgres, no load balancer.**
Every cloud piece is a **config-selected adapter behind a seam with a local default**, so
the same code runs fully locally *or* serverless:

| Seam | Local default | Cloud adapter |
|------|---------------|---------------|
| DB (`persistence/db`) | SQLite `file:` | Turso / libSQL (remote-only) |
| Job queue (`apps/api/jobs/queue`) | in-process ThreadPool | Cloud Tasks |
| Artifacts (`persistence/artifacts`) | local disk (inline) | GCS (signed URLs) |
| Scheduler | in-process APScheduler | Cloud Scheduler → worker |
| Onboarding agent runner | local Docker sandbox | GitHub Actions |

## Deployment (live on Cloud Run)
Serverless topology, all within free tiers: **3 Cloud Run services** (api · ingestor ·
worker) + **Turso** (DB) + **Cloud Tasks** (pipeline queue) + **Cloud Scheduler** (ingest
fast/slow + mailer) + **GCS** (artifacts) + **Secret Manager** + **Vercel** (web) +
**GitHub Actions** (build + `gcloud run deploy` on push to `main`). Provisioned by
`deploy/terraform/`. A `$5/mo VPS` running the same Docker Compose is the documented
fallback (serverless ↔ VPS is a redeploy, not a rewrite).

## Quickstart (local)
```bash
uv sync --all-extras                        # install (core + api + scrape + dev)
cp .env.example .env                         # set provider + RESUMAKER_API_TOKEN
# data/profile/profile.json (gitignored, holds PII) is the source of truth.

uv run python -m apps.cli run <jd-url>       # full pipeline, live progress
uv run python -m apps.cli serve              # API at :8000
uv run python -m apps.cli onboard "Databricks"   # add a company to the watchlist
uv run python -m apps.cli ingest --once      # poll the watchlist once
uv run python -m apps.cli discovery          # deterministic feed
uv run python -m apps.cli track add <jd-url> # add to the tracker (runs the match)
uv run python -m apps.cli costs              # LLM spend + Gemini budget

cd web && npm install && npm run dev         # dashboard at :3000 (talks to the API)
```
System deps for PDF + scraping fallback: `brew install --cask libreoffice` and
`uv run playwright install chromium` (the worker Docker image bundles LibreOffice +
Carlito + the Claude CLI).

## LLM engine
Provider-agnostic via `providers/llm` (`RESUMAKER_DEFAULT_PROVIDER`): **Claude CLI**
(subscription, $0 tokens — local + cloud via `CLAUDE_CODE_OAUTH_TOKEN`) · **Anthropic
API** (metered — headless fallback) · **Gemini** (hard-capped at $5). A `FallbackProvider`
fails over automatically (`RESUMAKER_FALLBACK_PROVIDER`). Deterministic (temp 0) calls are
cached. Current defaults: **Opus** for tailoring, **Sonnet** for the match.

## Grounding & safety
Everything traces to `data/profile/profile.json`; a mechanical **fact-gate** blocks any
metric/employer/title not in the profile. The extension capture endpoint is token-gated
and size-bounded. PII (`data/`), secrets (`.env`, `.secrets/`), and artifacts (`outputs/`)
are gitignored and never committed.

## Docs
- [`RESUME_SYSTEM_BLUEPRINT.md`](RESUME_SYSTEM_BLUEPRINT.md) — the *what/why* (21-topic ATS/recruiter playbook).
- [`TASKS.md`](TASKS.md) — the *how/when*: phased plan + the production-rebuild log (R0–R9, RI) + deployment (D) + platform (RA) + the post-deploy product log.
- [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md) — deep architecture write-up.

The validated pre-rebuild POCs are preserved in git (tag `poc-complete`, branch `legacy-pocs`) — the on-disk `legacy/` tree has been retired.

## License
Private. All rights reserved.
