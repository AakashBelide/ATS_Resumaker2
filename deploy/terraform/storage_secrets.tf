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

// Only non-empty secrets are created (optional ones stay out of Secret Manager entirely).
locals {
  secrets = merge(
    {
      "resumaker-api-token" = var.api_token
      "turso-database-url"  = var.turso_database_url
      "turso-auth-token"    = var.turso_auth_token
    },
    var.claude_code_oauth_token != "" ? { "claude-code-oauth-token" = var.claude_code_oauth_token } : {},
    var.anthropic_api_key != "" ? { "anthropic-api-key" = var.anthropic_api_key } : {},
    var.gemini_api_key != "" ? { "gemini-api-key" = var.gemini_api_key } : {},
  )
}

resource "google_secret_manager_secret" "s" {
  for_each  = local.secrets
  secret_id = each.key
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "v" {
  for_each    = local.secrets
  secret      = google_secret_manager_secret.s[each.key].id
  secret_data = each.value
}
