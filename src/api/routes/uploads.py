import subprocess
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.config import Settings
from src.jobs.store import CampaignStore
from src.storage.client import StorageClient

logger = structlog.get_logger()
router = APIRouter(prefix="/api", tags=["uploads"])


class SignedUrlRequest(BaseModel):
    campaign_id: str
    type: str  # "intro" or "main"
    filename: str
    content_type: str = "video/mp4"


class SignedUrlResponse(BaseModel):
    upload_url: str
    video_id: str
    gcs_path: str


class RegisterVideoRequest(BaseModel):
    video_id: str


@router.post("/upload/signed-url", response_model=SignedUrlResponse)
def get_signed_upload_url(body: SignedUrlRequest, request: Request) -> SignedUrlResponse:
    settings: Settings = request.app.state.settings
    store: CampaignStore = request.app.state.store
    gcs: StorageClient = request.app.state.gcs

    if body.type not in ("intro", "main"):
        raise HTTPException(status_code=400, detail="type must be 'intro' or 'main'")

    campaign = store.get_campaign(body.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    video_id = str(uuid.uuid4())
    user_id = campaign["user_id"]
    gcs_path = f"uploads/{user_id}/{body.type}s/{video_id}.mp4"

    # Create video record (metadata will be filled after upload)
    store.create_video(
        video_id=video_id,
        campaign_id=body.campaign_id,
        user_id=user_id,
        video_type=body.type,
        filename=body.filename,
        gcs_path=gcs_path,
    )

    upload_url = gcs.generate_signed_upload_url(
        bucket_name=settings.gcs_upload_bucket,
        blob_path=gcs_path,
        content_type=body.content_type,
        expiry_minutes=settings.signed_url_expiry_minutes,
    )

    logger.info("signed_url_generated", video_id=video_id, campaign_id=body.campaign_id)
    return SignedUrlResponse(upload_url=upload_url, video_id=video_id, gcs_path=gcs_path)


@router.post("/campaigns/{campaign_id}/videos")
def register_video(campaign_id: str, body: RegisterVideoRequest, request: Request) -> dict:
    """Called after browser uploads to GCS. Runs ffprobe to extract metadata."""
    settings: Settings = request.app.state.settings
    store: CampaignStore = request.app.state.store
    gcs: StorageClient = request.app.state.gcs

    video = store.get_video(body.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video["campaign_id"] != campaign_id:
        raise HTTPException(status_code=400, detail="Video does not belong to this campaign")

    # Get file size from GCS
    size = gcs.get_blob_size(settings.gcs_upload_bucket, video["gcs_path"])

    # Probe video metadata via GCS URI
    gcs_uri = f"gs://{settings.gcs_upload_bucket}/{video['gcs_path']}"
    metadata = _probe_gcs_video(gcs_uri)

    store.update_video(
        body.video_id,
        size_bytes=size,
        duration_seconds=metadata.get("duration_seconds"),
        codec=metadata.get("video_codec"),
        width=metadata.get("width"),
        height=metadata.get("height"),
    )

    updated = store.get_video(body.video_id)
    logger.info("video_registered", video_id=body.video_id, codec=metadata.get("video_codec"))
    return updated


def _probe_gcs_video(gcs_uri: str) -> dict:
    """Run ffprobe on a GCS URI. Requires gcloud auth configured."""
    import json

    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        gcs_uri,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        logger.warning("ffprobe_gcs_failed", uri=gcs_uri, stderr=result.stderr[:300])
        return {}

    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    video = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), None)

    return {
        "duration_seconds": float(fmt.get("duration", 0)),
        "video_codec": video["codec_name"] if video else None,
        "width": int(video["width"]) if video else None,
        "height": int(video["height"]) if video else None,
    }
