# ---------- Artifact Registry ----------

resource "google_artifact_registry_repository" "vgen" {
  location      = var.region
  repository_id = "vgen"
  format        = "DOCKER"
  description   = "VGen container images"

  depends_on = [google_project_service.apis]
}

# ---------- Cloud Build trigger ----------
# NOTE: GitHub connection must be set up manually first in Cloud Build console:
#   Cloud Build > Triggers > Connect Repository > GitHub
# After connecting, update github.owner and github.name below.

resource "google_cloudbuild_trigger" "deploy_on_push" {
  name     = "vgen-deploy-on-push"
  location = var.region

  github {
    owner = var.github_owner
    name  = var.github_repo

    push {
      branch = "^main$"
    }
  }

  filename = "cloudbuild.yaml"

  depends_on = [google_project_service.apis]
}

# ---------- Cloud Build IAM ----------
# Cloud Build default SA: {project_number}@cloudbuild.gserviceaccount.com

locals {
  cloudbuild_sa = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = local.cloudbuild_sa
}

resource "google_project_iam_member" "cloudbuild_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = local.cloudbuild_sa
}

resource "google_project_iam_member" "cloudbuild_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = local.cloudbuild_sa
}
