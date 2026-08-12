// Cloud Tasks work queue (api enqueues -> worker /run-pipeline + /tracker-match) + Cloud Scheduler
// cron jobs (-> ingestor /ingest-tick and /mailer-tick). All authenticate to the token-protected
// app via the X-API-Key header. Ingestion + email run on the lean `ingestor` service, not the api.

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

// Two ingestion cadences: clean boards often, gently-polled boards once daily. Both hit the
// ingestor service (isolated from user traffic + LLM work); 1800s deadline matches its timeout.
resource "google_cloud_scheduler_job" "ingest_fast" {
  name             = "resumaker-ingest-fast"
  schedule         = var.ingest_cron_fast
  time_zone        = var.scheduler_timezone
  region           = var.region
  attempt_deadline = "1800s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.ingestor.uri}/v1/worker/ingest-tick"
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
  attempt_deadline = "1800s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.ingestor.uri}/v1/worker/ingest-tick"
    headers = {
      "Content-Type" = "application/json"
      "X-API-Key"    = var.api_token
    }
    body = base64encode(jsonencode({ sources = "slow" }))
  }
  depends_on = [google_project_service.enabled]
}

// Dedicated email-digest job, decoupled from ingestion. Its cron IS the Mailer "frequency" - the
// app rewrites schedule/paused live from the Mailer page (approach B), so Terraform sets the
// initial value but doesn't fight later edits.
resource "google_cloud_scheduler_job" "mailer" {
  name             = "resumaker-mailer"
  schedule         = var.mailer_cron
  time_zone        = var.scheduler_timezone
  region           = var.region
  attempt_deadline = "320s" // a digest send is quick (query backlog + email)

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.ingestor.uri}/v1/worker/mailer-tick"
    headers = {
      "Content-Type" = "application/json"
      "X-API-Key"    = var.api_token
    }
  }
  depends_on = [google_project_service.enabled]

  lifecycle {
    ignore_changes = [schedule, paused]
  }
}
