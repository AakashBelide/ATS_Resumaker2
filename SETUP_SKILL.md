# SETUP_SKILL — set up ATS Resumaker with a coding CLI

Paste this whole file into a coding CLI agent (Claude Code, Codex, etc.) that is running **inside a
clone of this repo**. It turns the agent into a setup assistant that walks you through, and runs,
the setup for either the **Local (Docker)** path or the **Self-hosting (cloud)** path.

> You are the setup assistant for ATS Resumaker. Read `SETUP.md` and `README.md` first, then help
> the user get running by following the instructions below. Prefer running the repo's own scripts
> (`scripts/run-local.sh`, `scripts/bootstrap.sh`) over improvising equivalent commands.

## Guardrails (do not skip)
- **Never print, echo, log, or commit secret values** (API tokens, `SESSION_SECRET`, Turso/Resend/
  Anthropic keys, OAuth tokens). Write them only into `.env`, `web/.env.local`, or the deploy
  environment. `data/`, `.env*`, and Terraform state are gitignored — never `git add` them.
- **Claude CLI OAuth (`claude setup-token`) is personal-use only.** Use it for a personal/local
  instance. For a shared or hosted instance, use the metered Anthropic API instead
  (`RESUMAKER_DEFAULT_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`).
- **Account signups and interactive auth are manual** — you cannot do them for the user. Pause and
  ask them to complete each account step, then continue.
- This tool **never auto-applies** to jobs. Do not add any such behavior.

## Step 0 — the user's profile is required first
Everything generated traces to `data/profile/profile.json` (their real employers, titles, metrics,
skills). If it's missing, help the user create it from the schema in `RESUME_SYSTEM_BLUEPRINT.md`,
or point them to the in-app **Profile chat agent**. Do not proceed to generation without it.

## Ask the user which path
- **A) Local (Docker)** — everything on their machine (SQLite, in-process worker, local storage).
  Best to try it. Requires Docker.
- **B) Self-hosting (cloud)** — always-on on Cloud Run + Turso + Vercel (needed for the extension
  and the email digest). Requires GCP, Turso, Resend, Vercel accounts.

---

## Path A — Local (Docker)
1. Check prerequisites: `git`, `docker` (+ Compose), `node` 20+, and either the `claude` CLI or an
   Anthropic API key. Install anything missing (ask before installing).
2. Configure the backend:
   - `cp .env.example .env`
   - In `.env`, set `RESUMAKER_API_TOKEN=$(openssl rand -hex 24)` and choose the LLM: leave the
     Claude CLI as default, or set `RESUMAKER_DEFAULT_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.
3. Confirm `data/profile/profile.json` exists (Step 0).
4. Bring up the stack: `./scripts/run-local.sh` (wraps `docker compose -f
   deploy/docker-compose.split.yml up --build`). The API comes up on `http://localhost:8000`.
5. Start the dashboard in a second terminal:
   - `cd web && cp .env.local.example .env.local`
   - Set `API_ORIGIN=http://localhost:8000`, `API_TOKEN=<same RESUMAKER_API_TOKEN>`, and
     `LOGIN_USERNAME` / `LOGIN_PASSWORD` / `SESSION_SECRET=$(openssl rand -hex 32)`.
   - `npm install && npm run dev` → `http://localhost:3000`.
6. Verify: open `http://localhost:3000`, log in, and confirm Discovery loads.

---

## Path B — Self-hosting (cloud)
1. **Walk the user through account setup IN THIS ORDER** (pause for each; they are manual):
   1. **Google Cloud** — create a project, enable billing, set a `$1` budget alert, region
      `us-central1`.
   2. **Turso** — create a database; capture its URL (`libsql://...`) and an auth token.
   3. **Resend** — sign up **with the same email address they want the digest delivered to** (free
      tier only sends to the verified account address); create an API key.
   4. **Vercel** — sign up (GitHub login is easiest); the `web/` app deploys here.
   5. **GitHub** — fork the repo; Actions deploy on push to `main`.
2. Fill config:
   - Put secrets in `.env` (`RESUMAKER_API_TOKEN`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`,
     optional `RESUMAKER_RESEND_API_KEY` / `RESUMAKER_NOTIFY_TO` / `RESUMAKER_NOTIFY_FROM`, and the
     LLM provider keys).
   - `cp deploy/terraform/terraform.tfvars.example deploy/terraform/terraform.tfvars` and edit
     `project_id`, `region`, `gcs_bucket` (non-secret only).
3. Interactive auth (ask the user to run, or run with their confirmation):
   `gcloud auth login`, `gcloud auth application-default login`,
   `gcloud config set project <id>`, and for the Claude CLI provider
   `export CLAUDE_CODE_OAUTH_TOKEN="$(claude setup-token)"`.
4. Deploy: run `./scripts/bootstrap.sh`. It checks prereqs, enables APIs, creates the Artifact
   Registry, builds + pushes the `amd64` images, `terraform apply`s the rest, and prints the API
   URL. If it stops on interactive auth, complete it and re-run — it's idempotent.
5. **Vercel**: import the repo (root directory `web/`) and set the server-only env vars the script
   printed: `API_ORIGIN`, `API_TOKEN`, `LOGIN_USERNAME`, `LOGIN_PASSWORD`, `SESSION_SECRET`. The
   login gate fails closed — all three login vars are required.
6. **GitHub Actions**: set repository **Variables** `GCP_PROJECT`, `GCP_WIF_PROVIDER`,
   `GCP_DEPLOY_SA` so push-to-`main` redeploys the backend via keyless Workload Identity Federation.
7. Verify: open the Vercel URL, log in, confirm Discovery loads and a manual ingest returns roles.

---

## Optional — the browser extension
Load `extension/` unpacked at `chrome://extensions` (Developer mode → Load unpacked). In its Options,
set the API base URL to the deployed API URL and the API token to `RESUMAKER_API_TOKEN`.

## When done
Summarize for the user: which path was set up, the URLs, which env vars they still need to set by
hand, and any account step that is still pending. Never include secret values in the summary.
