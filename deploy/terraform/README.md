# resumaker — Terraform (Cloud Run serverless)

Provisions the whole $0-tier stack: **Artifact Registry**, two **Cloud Run** services (public
token-protected `api` + heavy `worker`), **Cloud Tasks** (pipeline queue), **Cloud Scheduler**
(two ingestion crons), **GCS** (artifacts), **Secret Manager**, and least-privilege **IAM**.

Everything is parameterized — nothing GCP-specific is hardcoded in the app. Local dev never needs
any of this (`docker compose up`); this is only for the cloud deploy.

## Prereqs
- `gcloud auth application-default login`, project set, **billing enabled**.
- Region `us-central1` (keeps GCS in the free tier).
- Terraform ≥ 1.6.

## Deploy (chicken-and-egg: Terraform references images, so push them first)

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars     # edit project/region/bucket

# 1) Secrets via env (never in tfvars/state-cleartext):
export TF_VAR_api_token="$(openssl rand -hex 24)"
export TF_VAR_turso_database_url="libsql://…"     TF_VAR_turso_auth_token="…"
export TF_VAR_claude_code_oauth_token="$(claude setup-token)"   # headless CLI auth
export TF_VAR_gemini_api_key="…"                  # if fallback_provider=gemini

# 2) Create ONLY the registry first, so we have somewhere to push:
terraform init
terraform apply -target=google_artifact_registry_repository.repo

# 3) Build + push both images (amd64 — Cloud Run arch; libsql wheels need it):
REPO="us-central1-docker.pkg.dev/$(gcloud config get-value project)/resumaker"
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build --platform linux/amd64 -f ../Dockerfile.api    -t "$REPO/api:latest"    ../..
docker build --platform linux/amd64 -f ../Dockerfile.worker -t "$REPO/worker:latest" ../..
docker push "$REPO/api:latest" && docker push "$REPO/worker:latest"

# 4) Now the rest (services reference those images):
terraform apply
```

`terraform output api_url` → set as `NEXT_PUBLIC_API_BASE` on Vercel.

## Existing bucket
If you already created `resumaker-bucket` by hand, import it so Terraform manages it instead of
failing on "already exists":
```bash
terraform import google_storage_bucket.artifacts resumaker-bucket
```

## Notes / follow-ups
- **Auth model:** both services are public but gated by the in-app token (`require_token`);
  Scheduler/Tasks present it as `X-API-Key`. Simpler than OIDC and matches the app code. A
  hardening pass (private worker + OIDC from a dedicated invoker SA) is a clean future step.
- **State** holds secret material (the Scheduler jobs embed the api token). It's local +
  gitignored; for a team, move to a GCS backend with restricted access (see `versions.tf`).
- **Free tier:** Cloud Run scales to zero; GCS in us-central1 (5 GB free, 90-day artifact
  expiry keeps it small); Scheduler (3 jobs free) and Tasks well within limits.
- `terraform destroy` tears it all down.
