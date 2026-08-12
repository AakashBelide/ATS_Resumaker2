terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # State is local by default (gitignored). For a team, point this at a GCS backend:
  #   backend "gcs" { bucket = "<tf-state-bucket>"; prefix = "resumaker" }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
