// All deployment inputs. Non-secret values go in terraform.tfvars; secrets are passed via
// TF_VAR_* env (never written to tfvars) and land in Secret Manager, not in state cleartext.

variable "project_id" {
  type        = string
  description = "GCP project id (e.g. gen-lang-client-0654703653)."
}

variable "region" {
  type        = string
  description = "Region for all resources. Use us-central1/us-east1/us-west1 to keep GCS free."
  default     = "us-central1"
}

variable "artifact_repo" {
  type        = string
  description = "Artifact Registry Docker repo name."
  default     = "resumaker"
}

variable "api_image" {
  type        = string
  description = "Full api image ref (…/resumaker/api:tag). Set after the first push."
}

variable "worker_image" {
  type        = string
  description = "Full worker image ref (…/resumaker/worker:tag). Set after the first push."
}

variable "gcs_bucket" {
  type        = string
  description = "Bucket for run artifacts. Created here; import an existing one with terraform import."
  default     = "resumaker-bucket"
}

// -- ingestion schedule (owner parameters) -----------------------------------------------------
variable "ingest_cron_fast" {
  type        = string
  description = "Cron for clean boards (Greenhouse/Lever/Ashby). Every 2h, 8am-10pm."
  default     = "0 8-22/2 * * *"
}

variable "ingest_cron_slow" {
  type        = string
  description = "Cron for gently-polled boards (Workday etc.). Once daily."
  default     = "0 9 * * *"
}

variable "scheduler_timezone" {
  type    = string
  default = "America/New_York"
}

// -- secrets (passed via TF_VAR_*, NOT tfvars; stored in Secret Manager) ------------------------
variable "api_token" {
  type        = string
  description = "Single-user API token the frontend/Scheduler/Tasks present."
  sensitive   = true
}

variable "turso_database_url" {
  type      = string
  sensitive = true
}

variable "turso_auth_token" {
  type      = string
  sensitive = true
}

variable "claude_code_oauth_token" {
  type        = string
  description = "Claude CLI subscription token (headless) for the worker's CLI-first LLM."
  sensitive   = true
  default     = ""
}

variable "fallback_provider" {
  type        = string
  description = "LLM failover engine when the CLI fails: '' | anthropic | gemini."
  default     = ""
}

variable "anthropic_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "gemini_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
