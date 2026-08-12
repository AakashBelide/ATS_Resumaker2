// Core: enable the APIs we use, the Artifact Registry repo, and the service accounts + IAM the
// services/triggers run as. Kept minimal and least-privilege for a single-user hobby deploy.

locals {
  apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each                   = toset(local.apis)
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}

// Docker repo the api/worker images are pushed to. Cleanup policies keep storage near $0: retain
// the few most-recent versions per image and delete anything older, so old tags don't accumulate
// past the 0.5 GB free tier.
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "resumaker container images (api + worker)"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" // 30 days
    }
  }

  depends_on = [google_project_service.enabled]
}

// --- service account --------------------------------------------------------------------------
// The identity both Cloud Run services run as: reads secret versions, owns objects in the
// artifact bucket, and enqueues Cloud Tasks. Services are public but token-protected in-app
// (require_token), so Scheduler/Tasks authenticate by presenting the api token header - no
// invoker SA / OIDC needed. Hardening to private worker + OIDC is a documented follow-up.
resource "google_service_account" "run" {
  account_id   = "resumaker-run"
  display_name = "resumaker Cloud Run (api + worker)"
}

resource "google_project_iam_member" "run_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_storage_bucket_iam_member" "run_bucket" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.run.email}"
}

resource "google_project_iam_member" "run_tasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.run.email}"
}
