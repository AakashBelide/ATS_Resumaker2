# ATS Resumaker

Accuracy-first system that turns a job-description URL into a grounded, ATS-optimized
**resume + cover letter + apply/no-apply decision** — traced strictly to a canonical
source-of-truth profile, with a hard anti-fabrication gate. Built from a study of three
prior projects plus 2026 research on how US ATS and recruiters actually screen.

## What it does
`JD URL → scrape → structure → keywords · gap · sponsorship (parallel) → fit → apply-decision → resume (tailor · deterministic skills · docx→pdf · fact-gate · ATS-verify · ATS-score) → cover letter`, plus a **job watchlist** that auto-onboards companies, polls their boards, dedupes new postings, and notifies you. Human-in-the-loop: it advises and drafts; it never auto-applies.

## Architecture (modular monolith, single-user, self-hostable)
```
src/resumaker/          # core library (pure domain logic)
  config/  domain/  observability/  persistence/(files + SQLite + cache)
  providers/  llm/(Claude CLI · Anthropic API · Gemini, registry + cache)
              scrape/(single JD)   sources/(board listing: greenhouse/lever/ashby/workday)
  stages/    scrape→...→resume, cover_letter, sponsorship/, resume/
  ats/       scorer · semantic · verify · skills_rank · fact_gate · sim/
  pipeline/  orchestrator (stage DAG) + progress
  enrichment/  ingestion/(onboard · service · scheduler · notify)
apps/api/   FastAPI (runs + SSE + watchlist + costs, token auth, in-process worker)
apps/cli/   run · watch · ingest · onboard · onboard-seed · schedule · costs · serve
web/  extension/   Next.js dashboard + MV3 extension (scaffolds)
deploy/     Dockerfile · docker-compose · Caddy · systemd
```
Right-sized on purpose: **no microservices, no Redis, no Postgres, no load balancer.**
SQLite (files canonical, DB derived), an in-process worker, and disk caches keep it free
to host and lightweight, with clean seams to scale up later.

## Quickstart
```bash
uv sync --all-extras                       # install (core + api + scrape + dev)
cp .env.example .env                        # set provider + RESUMAKER_API_TOKEN
# data/profile/profile.json (gitignored, holds PII) is the source of truth.

uv run python -m apps.cli run <jd-url>      # full pipeline, live progress
uv run python -m apps.cli serve             # API at :8000  (SSE, watchlist, costs)
uv run python -m apps.cli onboard "Databricks"     # add a company to the watchlist
uv run python -m apps.cli schedule --once   # poll the watchlist once
uv run python -m apps.cli costs             # LLM spend + Gemini budget
```
System deps for PDF + scraping fallback: `brew install --cask libreoffice` and
`uv run playwright install chromium` (the Docker image bundles LibreOffice + Carlito).

## LLM engine
Provider-agnostic via `providers/llm` (`RESUMAKER_DEFAULT_PROVIDER`): **Claude CLI**
(subscription, $0 tokens — great locally) · **Anthropic API** (credits — the engine for a
headless VM) · **Gemini** (hard-capped at $5). Deterministic (temp 0) calls are cached.

## Deploy (any host)
```bash
docker compose -f deploy/docker-compose.yml up -d --build   # API behind Caddy (auto-HTTPS)
```
Set `RESUMAKER_DEFAULT_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` on a VM (no Claude CLI),
`RESUMAKER_API_TOKEN` (auth), and `DOMAIN` for HTTPS. `data/` + `outputs/` are host-mounted.

## Grounding & safety
Everything traces to `data/profile/profile.json`; a mechanical **fact-gate** blocks any
metric/employer/title not in the profile. PII (`data/`), secrets (`.env`), and artifacts
(`outputs/`) are gitignored and never committed.

## Docs
- [`RESUME_SYSTEM_BLUEPRINT.md`](RESUME_SYSTEM_BLUEPRINT.md) — the *what/why* (21-topic ATS/recruiter playbook).
- [`TASKS.md`](TASKS.md) — the *how/when*: phased plan + the production-rebuild log (R0–R9, RI).
- [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md) — deep write-up of Phases 1–3.

The validated pre-rebuild POCs are preserved under `legacy/` (tag `poc-complete`, branch `legacy-pocs`).

## License
Private. All rights reserved.
