// The two Cloud Run services: a lean `api` and a heavy `worker`. Both scale to zero and are
// public but token-protected in-app (require_token): the frontend/Scheduler reach the api, and
// Cloud Tasks reaches the worker, each presenting the api token. (Private worker + OIDC is a
// documented hardening follow-up.)

locals {
  // Plain (non-secret) env shared by both services.
  common_env = {
    RESUMAKER_ENVIRONMENT       = "vm"
    RESUMAKER_ARTIFACT_BACKEND  = "gcs"
    RESUMAKER_GCS_BUCKET        = var.gcs_bucket
    RESUMAKER_GCP_PROJECT       = var.project_id
    RESUMAKER_GCP_REGION        = var.region
    RESUMAKER_FALLBACK_PROVIDER = var.fallback_provider
    RESUMAKER_SCHEDULER_ENABLED = "false" // cloud uses Cloud Scheduler, not the in-process loop
  }

  // env-var name -> Secret Manager secret_id, only for secrets that were actually created.
  api_secret_env = merge(
    {
      RESUMAKER_API_TOKEN = "resumaker-api-token"
      TURSO_DATABASE_URL  = "turso-database-url"
      TURSO_AUTH_TOKEN    = "turso-auth-token"
    },
    contains(local.active_secrets, "anthropic-api-key") ? { ANTHROPIC_API_KEY = "anthropic-api-key" } : {},
    contains(local.active_secrets, "gemini-api-key") ? { GEMINI_API_KEY = "gemini-api-key" } : {},
  )
  // The worker also gets the Claude CLI subscription token (CLI-first LLM).
  worker_secret_env = merge(
    local.api_secret_env,
    contains(local.active_secrets, "claude-code-oauth-token") ? { CLAUDE_CODE_OAUTH_TOKEN = "claude-code-oauth-token" } : {},
  )
}

resource "google_cloud_run_v2_service" "api" {
  name     = "resumaker-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.run.email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.api_image
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }

      dynamic "env" {
        for_each = merge(local.common_env, {
          RESUMAKER_JOB_QUEUE   = "cloud_tasks"
          RESUMAKER_WORKER_URL  = google_cloud_run_v2_service.worker.uri
          RESUMAKER_TASKS_QUEUE = google_cloud_tasks_queue.pipeline.name
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.api_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }
  depends_on = [google_project_service.enabled, google_secret_manager_secret_version.v]
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "resumaker-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL" // public but token-gated in-app; Cloud Tasks calls it with the token

  template {
    service_account = google_service_account.run.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    timeout = "1800s" // a pipeline run is minutes; Cloud Tasks awaits the response

    containers {
      image = var.worker_image
      resources {
        limits = { cpu = "1", memory = "2Gi" } // LibreOffice render headroom
      }

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.worker_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }
  depends_on = [google_project_service.enabled, google_secret_manager_secret_version.v]
}

// Both services are public but token-protected in-app: the frontend + Scheduler reach the api,
// and Cloud Tasks reaches the worker, each presenting the api token header.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "worker_public" {
  location = var.region
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
