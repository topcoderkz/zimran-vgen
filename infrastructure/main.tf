# ---------- Enable APIs ----------

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# ---------- Firestore ----------

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

# ---------- Service Accounts ----------

resource "google_service_account" "api" {
  account_id   = "vgen-api"
  display_name = "VGen API Service Account"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "worker" {
  account_id   = "vgen-worker"
  display_name = "VGen Worker Service Account"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/datastore.user",
    "roles/storage.objectAdmin",
    "roles/pubsub.publisher",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/iam.serviceAccountTokenCreator",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "worker_roles" {
  for_each = toset([
    "roles/datastore.user",
    "roles/storage.objectAdmin",
    "roles/pubsub.subscriber",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/iam.serviceAccountTokenCreator",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# ---------- GCS Buckets ----------

resource "google_storage_bucket" "uploads" {
  name                        = "${var.project_id}-vgen-uploads"
  location                    = var.region
  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["PUT", "GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  lifecycle_rule {
    condition { age = 30 }
    action { type = "Delete" }
  }
}

resource "google_storage_bucket" "outputs" {
  name                        = "${var.project_id}-vgen-outputs"
  location                    = var.region
  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type", "Content-Disposition"]
    max_age_seconds = 3600
  }

  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }
}

# ---------- Pub/Sub ----------

resource "google_pubsub_topic" "dlq" {
  name       = "merge-tasks-dlq"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "merge_tasks" {
  name       = "merge-tasks"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "worker" {
  name  = "merge-tasks-sub"
  topic = google_pubsub_topic.merge_tasks.id

  ack_deadline_seconds       = 600
  message_retention_duration = "604800s"

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }
}

# Grant Pub/Sub permission to publish to DLQ
resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  topic  = google_pubsub_topic.dlq.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

data "google_project" "current" {
  project_id = var.project_id
}

# ---------- Cloud Run: API ----------

resource "google_cloud_run_v2_service" "api" {
  name     = "vgen-api"
  location = var.region

  template {
    service_account = google_service_account.api.email

    containers {
      image = var.backend_image != "" ? var.backend_image : "${var.region}-docker.pkg.dev/${var.project_id}/vgen/backend:latest"

      ports {
        container_port = 8080
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCS_UPLOAD_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "GCS_OUTPUT_BUCKET"
        value = google_storage_bucket.outputs.name
      }
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.merge_tasks.name
      }
      env {
        name  = "CORS_ORIGINS"
        value = var.frontend_url
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# ---------- Cloud Run: Worker ----------

resource "google_cloud_run_v2_service" "worker" {
  name     = "vgen-worker"
  location = var.region

  template {
    service_account                  = google_service_account.worker.email
    max_instance_request_concurrency = 1

    containers {
      image   = var.backend_image != "" ? var.backend_image : "${var.region}-docker.pkg.dev/${var.project_id}/vgen/backend:latest"
      command = ["python", "-m", "src.worker.consumer"]

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCS_UPLOAD_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "GCS_OUTPUT_BUCKET"
        value = google_storage_bucket.outputs.name
      }
      env {
        name  = "PUBSUB_SUBSCRIPTION"
        value = google_pubsub_subscription.worker.name
      }

      resources {
        limits = {
          cpu    = "4"
          memory = "8Gi"
        }
      }
    }

    timeout = "1800s"
  }

  depends_on = [google_project_service.apis]
}

# ---------- Cloud Run: Frontend ----------

resource "google_cloud_run_v2_service" "frontend" {
  name     = "vgen-frontend"
  location = var.region

  template {
    containers {
      image = var.frontend_image != "" ? var.frontend_image : "${var.region}-docker.pkg.dev/${var.project_id}/vgen/frontend:latest"

      ports {
        container_port = 80
      }

      env {
        name  = "VITE_API_URL"
        value = "${google_cloud_run_v2_service.api.uri}/api"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Public access for frontend
resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------- Monitoring ----------

resource "google_monitoring_dashboard" "vgen" {
  dashboard_json = jsonencode({
    displayName = "VGen"
    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "Videos Processed"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/video_merger/videos_processed\""
                }
              }
            }]
          }
        },
        {
          title = "Processing Time (ms)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/video_merger/processing_time_ms\""
                }
              }
            }]
          }
        },
        {
          title = "Errors"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/video_merger/errors\""
                }
              }
            }]
          }
        },
        {
          title = "Pub/Sub Unacked Messages"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" resource.type=\"pubsub_subscription\""
                }
              }
            }]
          }
        },
      ]
    }
  })
}
