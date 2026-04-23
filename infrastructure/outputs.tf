output "api_url" {
  description = "URL of the API service"
  value       = google_cloud_run_v2_service.api.uri
}

output "frontend_url" {
  description = "URL of the frontend service"
  value       = google_cloud_run_v2_service.frontend.uri
}

output "worker_service" {
  description = "Worker Cloud Run service name"
  value       = google_cloud_run_v2_service.worker.name
}

output "upload_bucket" {
  description = "GCS bucket for uploads"
  value       = google_storage_bucket.uploads.name
}

output "output_bucket" {
  description = "GCS bucket for merged outputs"
  value       = google_storage_bucket.outputs.name
}

output "pubsub_topic" {
  description = "Pub/Sub topic for merge tasks"
  value       = google_pubsub_topic.merge_tasks.name
}

output "api_service_account" {
  value = google_service_account.api.email
}

output "worker_service_account" {
  value = google_service_account.worker.email
}
