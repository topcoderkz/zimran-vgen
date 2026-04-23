variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "backend_image" {
  description = "Container image for backend (API + worker)"
  type        = string
  default     = ""
}

variable "frontend_image" {
  description = "Container image for frontend"
  type        = string
  default     = ""
}

variable "frontend_url" {
  description = "Frontend Cloud Run URL (for API CORS)"
  type        = string
  default     = ""
}

variable "github_owner" {
  description = "GitHub repository owner (user or org)"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "zimran-vgen"
}

variable "alert_email" {
  description = "Email address for monitoring alert notifications"
  type        = string
  default     = "sandbox1@zimran.io"
}
