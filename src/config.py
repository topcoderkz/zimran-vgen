from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # GCP
    gcp_project_id: str
    gcp_region: str = "us-central1"

    # Cloud Storage
    gcs_upload_bucket: str
    gcs_output_bucket: str

    # Pub/Sub
    pubsub_topic: str = "merge-tasks"
    pubsub_subscription: str = "merge-tasks-sub"
    pubsub_dlq_topic: str = "merge-tasks-dlq"
    pubsub_dlq_subscription: str = "merge-tasks-dlq-sub"

    # Firestore
    firestore_collection_prefix: str = ""

    # Worker
    worker_max_retries: int = 5

    # Signed URLs
    signed_url_expiry_minutes: int = 60

    # Logging
    log_level: str = "INFO"

    # CORS
    cors_origins: str = ""

    # App
    app_version: str = "1.0.0"

    def collection(self, name: str) -> str:
        """Return prefixed Firestore collection name."""
        if self.firestore_collection_prefix:
            return f"{self.firestore_collection_prefix}_{name}"
        return name


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
