# ATS Resumaker, Setup Guide

Two ways to run it: **(A) Local (Docker)** on your own machine, or **(B) Self-hosting (cloud)** on
Google Cloud Run + Turso + Vercel within their free tiers. Start with **Local** to try it; move to
**Self-hosting** when you want it always-on and reachable from anywhere (including the browser
extension and the email digest).

> This same guide is rendered in-app at **`/setup`**. There's also a **`SETUP_SKILL.md`** you can
> paste into Claude (or any CLI agent) to have it walk you through, and run, these steps.

---

## 0. Before you start

### 0.1 Prerequisites to install

| Tool | For | Install |
|------|-----|---------|
| **git** | cloning the repo | https://git-scm.com |
| **Docker + Compose** | local run (required) | https://docs.docker.com/get-docker/ |
| **uv** | Python runtime (CLI/dev) | https://docs.astral.sh/uv/ |
| **Node 20+** | the web dashboard | https://nodejs.org |
| **Claude CLI** | the default LLM engine (subscription) | https://docs.claude.com/claude-code |
| *(cloud only)* **gcloud CLI** | GCP | https://cloud.google.com/sdk/docs/install |
| *(cloud only)* **Terraform >= 1.6** | provisioning | https://developer.hashicorp.com/terraform |
| *(cloud only)* **Turso CLI** | the database | https://docs.turso.tech/cli |

### 0.2 Your profile is the source of truth (required before onboarding)

Everything the system generates traces to **`data/profile/profile.json`**, your real employers,
titles, metrics, and skills. **Create it before you tail or generate anything.** Two ways:

- **Hand-write it** from the schema (see `RESUME_SYSTEM_BLUEPRINT.md`), or
- **Use the in-app Profile chat agent** (Profile page), it interviews you and proposes structured
  entries you approve. This is the easiest way for a new user to bootstrap a profile.

`data/` is gitignored and holds PII, it never leaves your machine / your bucket.

### 0.3 Disclaimers (read these)

- **Cost:** the cloud path is designed to fit **free tiers**, Cloud Run (240k vCPU-sec / 450k
  GiB-sec / month), Turso (3 GB syncs), GCS (5 GB, us-central1), Cloud Scheduler (3 free jobs),
  GitHub Actions (2000 min/mo), Vercel (hobby). Real single-user usage stays well inside these. You
  still attach a billing account to GCP, set a **$1 budget alert** so there are no surprises.
- **Claude CLI via OAuth is for PERSONAL use only.** `claude setup-token` gives a token for *your*
  subscription. Running a personal subscription on a shared/hosted server may violate Anthropic's
  ToS and hit rate limits. For a "real" hosted instance, use the **metered Anthropic API**
  (`RESUMAKER_DEFAULT_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`) instead.
- **Human-in-the-loop:** the system advises and drafts. It never auto-applies.

### 0.4 Choosing the Claude model (subscription tiers)

The LLM model is env-selectable, so pick per your subscription/usage budget:

```bash
RESUMAKER_MODEL_FAST=claude-haiku-4-5        # cheap extraction passes
RESUMAKER_MODEL_STANDARD=claude-sonnet-4-5   # structuring / analysis / match
RESUMAKER_MODEL_QUALITY=claude-opus-4-8      # tailoring / fact-critical
```

Lower-usage plan? A **budget preset**, Sonnet for standard+quality, Haiku for fast, keeps quality
high at lower cost. (Defaults above are the recommended balance.)

---

## A. Local (Docker)

The whole stack runs on your machine, SQLite (a local file), the in-process scheduler/worker, and
local artifact storage. No GCP/Turso/Vercel needed. **Docker is required.**

```bash
# 1) Clone
git clone <your-fork-url> ats-resumaker && cd ats-resumaker

# 2) Configure
cp .env.example .env
#    In .env, set at minimum:
#      RESUMAKER_API_TOKEN=$(openssl rand -hex 24)     # a token for the API
#      (LLM) either leave Claude CLI as default, or set RESUMAKER_DEFAULT_PROVIDER=anthropic + ANTHROPIC_API_KEY

# 3) Put your profile at data/profile/profile.json (see §0.2)

# 4) Bring it up (api + worker; LibreOffice + Claude CLI are baked into the worker image)
./scripts/run-local.sh          # wraps: docker compose -f deploy/docker-compose.split.yml up --build
#    API -> http://localhost:8000

# 5) The dashboard (separate terminal)
cd web
cp .env.local.example .env.local
#    set API_ORIGIN=http://localhost:8000 and API_TOKEN=<same RESUMAKER_API_TOKEN>
#    set LOGIN_USERNAME / LOGIN_PASSWORD / SESSION_SECRET (openssl rand -hex 32) to enable login
npm install && npm run dev      # http://localhost:3000
```

**Prefer the CLI?** Without Docker you can also run the library directly:

```bash
uv sync --all-extras
uv run python -m apps.cli serve                 # API at :8000
uv run python -m apps.cli onboard "Databricks"  # add a company to the watchlist
uv run python -m apps.cli run <jd-url>          # full pipeline on one posting
```
(System deps for the CLI path: `brew install --cask libreoffice` + `uv run playwright install chromium`.)

---

## B. Self-hosting (cloud, GCP + Turso + Vercel)

Serverless, scale-to-zero, free-tier. **Do the account setup in this order**, a couple of small
details matter and are called out.

### B.1 Accounts (in order)

1. **Google Cloud**, create a project, **enable billing**, set a **$1 budget alert**. Region
   **`us-central1`** (keeps GCS free).
2. **Turso**, sign up, create a database, grab its **URL** (`libsql://...`) and an **auth token**.
3. **Resend**, sign up **with the SAME email address you want the job digest delivered to** (on the
   free tier Resend only sends to your own verified address). Create an API key. This is easy to get
   wrong, the digest silently won't arrive if the recipient isn't your Resend account email.
4. **Vercel**, sign up (GitHub login is easiest); you'll deploy the `web/` app here.
5. **GitHub**, fork/clone the repo; Actions will build + deploy on push to `main`.

### B.2 Auth (interactive, can't be scripted away)

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project <YOUR_PROJECT_ID>
export CLAUDE_CODE_OAUTH_TOKEN="$(claude setup-token)"   # personal-use only (see §0.3)
```

### B.3 Fill in secrets, then deploy

Put your keys in `.env` (backend) and `deploy/terraform/terraform.tfvars` (project/region/bucket).
Then run the bootstrap script, which automates the scriptable parts:

```bash
cp deploy/terraform/terraform.tfvars.example deploy/terraform/terraform.tfvars   # edit project/region/bucket
./scripts/bootstrap.sh
```

`bootstrap.sh` will: check prerequisites -> enable the required GCP APIs -> push your secrets into
**Secret Manager** -> `terraform apply` (Artifact Registry, 2 Cloud Run services, Cloud Tasks, Cloud
Scheduler crons, GCS bucket, IAM) -> build + push the `amd64` images -> provision the Turso schema ->
print the API URL. It prompts you for any interactive auth it still needs.

<details><summary>Prefer to run it by hand? (what the script does)</summary>

```bash
cd deploy/terraform
export TF_VAR_api_token="$(openssl rand -hex 24)"
export TF_VAR_turso_database_url="libsql://..."  TF_VAR_turso_auth_token="..."
export TF_VAR_claude_code_oauth_token="$CLAUDE_CODE_OAUTH_TOKEN"
export TF_VAR_resend_api_key="..."  TF_VAR_notify_to="you@example.com"  TF_VAR_notify_from="you@example.com"

terraform init
terraform apply -target=google_artifact_registry_repository.repo      # registry first

REPO="us-central1-docker.pkg.dev/$(gcloud config get-value project)/resumaker"
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build --platform linux/amd64 -f ../Dockerfile.api    -t "$REPO/api:latest"    ../..
docker build --platform linux/amd64 -f ../Dockerfile.worker -t "$REPO/worker:latest" ../..
docker push "$REPO/api:latest" && docker push "$REPO/worker:latest"

terraform apply                                                       # the rest
terraform output api_url                                              # -> Vercel API_ORIGIN
```
</details>

### B.4 The web app on Vercel

Import the repo into Vercel, set the **root directory to `web/`**, and set these **server-only** env
vars (never `NEXT_PUBLIC_*`, the BFF keeps the token off the browser):

| Var | Value |
|-----|-------|
| `API_ORIGIN` | `terraform output api_url` (the Cloud Run api URL) |
| `API_TOKEN` | the same value as `RESUMAKER_API_TOKEN` |
| `LOGIN_USERNAME` | your login user |
| `LOGIN_PASSWORD` | your login password |
| `SESSION_SECRET` | `openssl rand -hex 32` |

> ⚠️ The login gate **fails closed**, if `LOGIN_USERNAME` / `LOGIN_PASSWORD` / `SESSION_SECRET`
> aren't set on Vercel, the deployed app locks everyone out. Set all three.

### B.5 The browser extension (optional)

Load `extension/` unpacked (`chrome://extensions` -> Developer mode -> Load unpacked). In its Options,
set the **API base URL** to your Cloud Run api URL and the **API token** to `RESUMAKER_API_TOKEN`.
The extension talks to the backend directly (not through the web app), so it's independent of login.

### B.6 Tear down

`cd deploy/terraform && terraform destroy` removes everything.

---

## Troubleshooting

- **Digest email never arrives** -> on Resend's free tier the recipient must be your Resend
  account/verified email (§B.1.3).
- **`libsql` build fails** -> build images with `--platform linux/amd64` (no arm64 wheel).
- **App locked out after deploy** -> set `LOGIN_USERNAME` / `LOGIN_PASSWORD` / `SESSION_SECRET` on
  Vercel (§B.4).
- **LLM auth on the server** -> `claude setup-token` is personal-use; for a hosted instance prefer
  `RESUMAKER_DEFAULT_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.
