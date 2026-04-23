# ---------- Artifact Registry ----------

resource "google_artifact_registry_repository" "vgen" {
  location      = var.region
  repository_id = "vgen"
  format        = "DOCKER"
  description   = "VGen container images"

  depends_on = [google_project_service.apis]
}

# ---------- Cloud Build trigger ----------
# Created manually after connecting GitHub repo in Cloud Build console.
# To create via CLI:
#   gcloud builds triggers create github \
#     --repo-name=zimran-vgen --repo-owner=topcoderkz \
#     --branch-pattern="^main$" --build-config=cloudbuild.yaml \
#     --region=us-central1 --project=sandbox-456317

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
