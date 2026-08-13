#!/usr/bin/env bash
# scripts/bootstrap.sh - one-shot cloud provisioner for the self-hosting (cloud) path.
# See SETUP.md section B and the in-app /setup guide. Automates the scriptable parts:
#   prereq check -> interactive auth -> enable APIs + registry -> build/push amd64 images
#   -> terraform apply (Cloud Run x2, Cloud Tasks, Cloud Scheduler, GCS, Secret Manager, IAM)
#   -> print the API URL. Accounts and interactive auth stay manual (documented).
#
# Secrets are read from .env and passed to Terraform via TF_VAR_* env only (never written to
# tfvars or state cleartext). Re-running is safe; Terraform reconciles to the desired state.
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf '\033[1;34m>>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m!!\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. prerequisites -------------------------------------------------------------------------
for bin in gcloud terraform docker; do
  command -v "$bin" >/dev/null 2>&1 || die "missing '$bin' (see SETUP.md prerequisites)"
done
[ -f .env ] || die "copy .env.example to .env and fill in your secrets first"
TFDIR="deploy/terraform"
[ -f "$TFDIR/terraform.tfvars" ] || die "cp $TFDIR/terraform.tfvars.example $TFDIR/terraform.tfvars and edit project/region/bucket"

# load .env into the environment
set -a; . ./.env; set +a

# non-secret config comes from tfvars (project/region)
tfval() { grep -E "^[[:space:]]*$1[[:space:]]*=" "$TFDIR/terraform.tfvars" | head -1 | sed -E 's/.*=[[:space:]]*"?([^"]*)"?.*/\1/'; }
PROJECT="$(tfval project_id)"; [ -n "$PROJECT" ] || die "set project_id in $TFDIR/terraform.tfvars"
REGION="$(tfval region)"; REGION="${REGION:-us-central1}"
REPO_PATH="${REGION}-docker.pkg.dev/${PROJECT}/resumaker"
say "project=$PROJECT  region=$REGION"

# --- 1. interactive auth (cannot be scripted away) --------------------------------------------
gcloud config set project "$PROJECT" >/dev/null
gcloud auth print-access-token >/dev/null 2>&1 || gcloud auth login
gcloud auth application-default print-access-token >/dev/null 2>&1 || gcloud auth application-default login
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && command -v claude >/dev/null 2>&1; then
  read -rp ">> generate a Claude CLI token now (personal-use only)? [y/N] " ans
  [ "${ans:-N}" = "y" ] && CLAUDE_CODE_OAUTH_TOKEN="$(claude setup-token)"
fi

# --- 2. secrets -> TF_VAR_* -------------------------------------------------------------------
export TF_VAR_api_token="${RESUMAKER_API_TOKEN:?set RESUMAKER_API_TOKEN in .env}"
export TF_VAR_turso_database_url="${TURSO_DATABASE_URL:?set TURSO_DATABASE_URL in .env}"
export TF_VAR_turso_auth_token="${TURSO_AUTH_TOKEN:?set TURSO_AUTH_TOKEN in .env}"
export TF_VAR_claude_code_oauth_token="${CLAUDE_CODE_OAUTH_TOKEN:-}"
export TF_VAR_resend_api_key="${RESUMAKER_RESEND_API_KEY:-${RESEND_API_KEY:-}}"
export TF_VAR_notify_to="${RESUMAKER_NOTIFY_TO:-${NOTIFY_TO:-}}"
export TF_VAR_notify_from="${RESUMAKER_NOTIFY_FROM:-${NOTIFY_FROM:-onboarding@resend.dev}}"
export TF_VAR_api_image="${REPO_PATH}/api:latest"
export TF_VAR_worker_image="${REPO_PATH}/worker:latest"
[ -n "${RESUMAKER_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}" ] && export TF_VAR_github_token="${RESUMAKER_GITHUB_TOKEN:-$GITHUB_TOKEN}"

# --- 3. enable APIs + create the Artifact Registry first --------------------------------------
say "terraform init"
terraform -chdir="$TFDIR" init -input=false
say "enabling GCP APIs + Artifact Registry (this can take a minute)"
terraform -chdir="$TFDIR" apply -input=false -auto-approve \
  -target=google_project_service.enabled \
  -target=google_artifact_registry_repository.repo

# --- 4. build + push the amd64 images ---------------------------------------------------------
say "building + pushing images (linux/amd64 - required for Cloud Run + libsql wheels)"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" -q
docker build --platform linux/amd64 -f deploy/Dockerfile.api    -t "$REPO_PATH/api:latest"    .
docker build --platform linux/amd64 -f deploy/Dockerfile.worker -t "$REPO_PATH/worker:latest" .
docker push "$REPO_PATH/api:latest"
docker push "$REPO_PATH/worker:latest"

# --- 5. provision everything else -------------------------------------------------------------
say "terraform apply (Cloud Run, Tasks, Scheduler, GCS, Secret Manager, IAM)"
terraform -chdir="$TFDIR" apply -input=false -auto-approve

# --- 6. done ----------------------------------------------------------------------------------
API_URL="$(terraform -chdir="$TFDIR" output -raw api_url)"
cat <<DONE

$(say "deployed. API URL: $API_URL")

Next, import the repo into Vercel (root directory = web/) and set these server-only env vars:
  API_ORIGIN     = $API_URL
  API_TOKEN      = <same as RESUMAKER_API_TOKEN>
  LOGIN_USERNAME = <your login user>
  LOGIN_PASSWORD = <your login password>
  SESSION_SECRET = \$(openssl rand -hex 32)

The database schema is created automatically on the first API boot.
Tear down anytime with:  terraform -chdir=$TFDIR destroy
DONE
