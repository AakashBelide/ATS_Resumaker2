// GCS bucket for run artifacts + the app secrets in Secret Manager.

resource "google_storage_bucket" "artifacts" {
  name                        = var.gcs_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  // Artifacts are regenerable and small; expire them so storage stays well under the 5 GB free tier.
  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }

  depends_on = [google_project_service.enabled]
}

// Secret name -> value. Only names with a non-empty value are created (optional keys may be
// blank). The presence filter derives from sensitive vars, so the resulting NAME set is wrapped
// in nonsensitive() - the names are plain literals (never the secret material), which is exactly
// what may be exposed as for_each keys. This avoids "sensitive values cannot be used in for_each".
locals {
  secret_values = {
    "resumaker-api-token"     = var.api_token
    "turso-database-url"      = var.turso_database_url
    "turso-auth-token"        = var.turso_auth_token
    "claude-code-oauth-token" = var.claude_code_oauth_token
    "anthropic-api-key"       = var.anthropic_api_key
    "gemini-api-key"          = var.gemini_api_key
    "github-token"            = var.github_token
  }
  active_secrets = nonsensitive(toset([for k, v in local.secret_values : k if v != ""]))
}

resource "google_secret_manager_secret" "s" {
  for_each  = local.active_secrets
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "v" {
  for_each    = local.active_secrets
  secret      = google_secret_manager_secret.s[each.key].id
  secret_data = local.secret_values[each.key]
}
