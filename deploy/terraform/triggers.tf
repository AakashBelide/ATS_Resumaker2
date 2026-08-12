// Cloud Tasks work queue (api enqueues -> worker /run-pipeline) + Cloud Scheduler cron jobs
// (-> api /ingest-tick). Both authenticate to the token-protected app via the X-API-Key header.

resource "google_cloud_tasks_queue" "pipeline" {
  name     = "resumaker-pipeline"
  location = var.region

  rate_limits {
    max_dispatches_per_second = 1
    max_concurrent_dispatches = 2
  }
  retry_config {
    max_attempts  = 3
    min_backoff   = "10s"
    max_backoff   = "300s"
    max_doublings = 3
  }
  depends_on = [google_project_service.enabled]
}

// Two ingestion cadences: clean boards every 2h (8am-10pm ET), gently-polled boards once daily.
resource "google_cloud_scheduler_job" "ingest_fast" {
  name             = "resumaker-ingest-fast"
  schedule         = var.ingest_cron_fast
  time_zone        = var.scheduler_timezone
  region           = var.region
  attempt_deadline = "600s" // default is 180s; a full watchlist sweep can exceed it

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/worker/ingest-tick"
    headers = {
      "Content-Type" = "application/json"
      "X-API-Key"    = var.api_token
    }
    body = base64encode(jsonencode({ sources = "fast" }))
  }
  depends_on = [google_project_service.enabled]
}

resource "google_cloud_scheduler_job" "ingest_slow" {
  name             = "resumaker-ingest-slow"
  schedule         = var.ingest_cron_slow
  time_zone        = var.scheduler_timezone
  region           = var.region
  attempt_deadline = "600s" // default is 180s; a full watchlist sweep can exceed it

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/worker/ingest-tick"
    headers = {
      "Content-Type" = "application/json"
      "X-API-Key"    = var.api_token
    }
    body = base64encode(jsonencode({ sources = "slow" }))
  }
  depends_on = [google_project_service.enabled]
}
