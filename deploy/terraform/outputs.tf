output "api_url" {
  description = "Public api base URL - set NEXT_PUBLIC_API_BASE (Vercel) to this."
  value       = google_cloud_run_v2_service.api.uri
}

output "worker_url" {
  description = "Worker base URL (Cloud Tasks target). Also fed to the api as RESUMAKER_WORKER_URL."
  value       = google_cloud_run_v2_service.worker.uri
}

output "artifact_registry" {
  description = "Docker repo path to push api/worker images to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}"
}

output "run_service_account" {
  value = google_service_account.run.email
}
