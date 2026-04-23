import datetime

import structlog
from google.cloud import storage

logger = structlog.get_logger()


class StorageClient:
    """Wrapper around GCS for signed URLs and file transfer."""

    def __init__(self, project_id: str) -> None:
        self._client = storage.Client(project=project_id)

    def generate_signed_upload_url(
        self,
        bucket_name: str,
        blob_path: str,
        content_type: str = "video/mp4",
        expiry_minutes: int = 60,
    ) -> str:
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiry_minutes),
            method="PUT",
            content_type=content_type,
        )
        logger.debug("signed_upload_url_generated", bucket=bucket_name, path=blob_path)
        return url

    def generate_signed_download_url(
        self,
        bucket_name: str,
        blob_path: str,
        expiry_minutes: int = 60,
    ) -> str:
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiry_minutes),
            method="GET",
        )
        logger.debug("signed_download_url_generated", bucket=bucket_name, path=blob_path)
        return url

    def download_to_file(self, bucket_name: str, blob_path: str, local_path: str) -> str:
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.download_to_filename(local_path)
        logger.info("gcs_download_complete", bucket=bucket_name, path=blob_path, local=local_path)
        return local_path

    def upload_from_file(self, bucket_name: str, blob_path: str, local_path: str) -> str:
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(local_path, content_type="video/mp4")
        logger.info("gcs_upload_complete", bucket=bucket_name, path=blob_path)
        return f"gs://{bucket_name}/{blob_path}"

    def get_blob_size(self, bucket_name: str, blob_path: str) -> int | None:
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.reload()
        return blob.size
