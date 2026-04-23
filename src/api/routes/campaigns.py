import itertools
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.config import Settings
from src.jobs.store import CampaignStore
from src.pubsub.publisher import MergePublisher

logger = structlog.get_logger()
router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class QualitySettings(BaseModel):
    codec: str = "copy"
    resolution: str = "original"
    crf: int | None = None
    audio_bitrate: str = "original"


class CreateCampaignRequest(BaseModel):
    name: str
    quality: QualitySettings = QualitySettings()


class StartCampaignResponse(BaseModel):
    status: str
    total_combinations: int


@router.post("")
def create_campaign(body: CreateCampaignRequest, request: Request) -> dict:
    store: CampaignStore = request.app.state.store
    campaign_id = str(uuid.uuid4())
    # TODO: extract user_id from auth token
    user_id = "default_user"
    return store.create_campaign(campaign_id, user_id, body.name, body.quality.model_dump())


@router.get("")
def list_campaigns(request: Request) -> list[dict]:
    store: CampaignStore = request.app.state.store
    user_id = "default_user"
    return store.list_campaigns(user_id)


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str, request: Request) -> dict:
    store: CampaignStore = request.app.state.store
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str, request: Request) -> None:
    store: CampaignStore = request.app.state.store
    store.delete_campaign(campaign_id)


@router.post("/{campaign_id}/start", response_model=StartCampaignResponse)
def start_campaign(campaign_id: str, request: Request) -> StartCampaignResponse:
    store: CampaignStore = request.app.state.store
    settings: Settings = request.app.state.settings
    publisher: MergePublisher = request.app.state.publisher

    campaign = store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["status"] != "draft":
        raise HTTPException(status_code=400, detail=f"Campaign is already {campaign['status']}")

    intros = store.list_videos(campaign_id, video_type="intro")
    mains = store.list_videos(campaign_id, video_type="main")

    if not intros or not mains:
        raise HTTPException(status_code=400, detail="Need at least one intro and one main video")

    # Generate all combinations
    combo_docs = []
    combo_messages = []
    for intro, main in itertools.product(intros, mains):
        combo_id = str(uuid.uuid4())
        output_path = f"outputs/{campaign_id}/{combo_id}.mp4"

        combo_docs.append({
            "id": combo_id,
            "campaign_id": campaign_id,
            "intro_video_id": intro["id"],
            "main_video_id": main["id"],
            "status": "pending",
            "output_gcs_path": output_path,
            "output_size_bytes": None,
            "output_duration": None,
            "error": None,
            "attempts": 0,
            "started_at": None,
            "completed_at": None,
        })

        combo_messages.append({
            "combination_id": combo_id,
            "campaign_id": campaign_id,
            "intro_gcs_path": intro["gcs_path"],
            "main_gcs_path": main["gcs_path"],
            "output_gcs_path": output_path,
            "quality": campaign["quality"],
        })

    # Batch write combinations to Firestore
    store.create_combinations_batch(combo_docs)

    # Update campaign status
    total = len(combo_docs)
    store.start_campaign(campaign_id, total)

    # Fan-out to Pub/Sub
    publisher.publish_combinations(combo_messages)

    logger.info("campaign_started", campaign_id=campaign_id, total_combinations=total)
    return StartCampaignResponse(status="processing", total_combinations=total)


@router.post("/{campaign_id}/combinations/{combination_id}/retry")
def retry_combination(campaign_id: str, combination_id: str, request: Request) -> dict:
    store: CampaignStore = request.app.state.store
    publisher: MergePublisher = request.app.state.publisher

    combo = store.get_combination(combination_id)
    if not combo:
        raise HTTPException(status_code=404, detail="Combination not found")
    if combo["status"] != "failed":
        raise HTTPException(status_code=400, detail=f"Combination is {combo['status']}, not failed")

    campaign = store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    intro = store.get_video(combo["intro_video_id"])
    main = store.get_video(combo["main_video_id"])
    if not intro or not main:
        raise HTTPException(status_code=400, detail="Source video(s) missing")

    # Reset combination and adjust campaign counts
    store.reset_combination_for_retry(combination_id)
    store.decrement_failed(campaign_id)

    # Republish to Pub/Sub
    publisher.publish_combination({
        "combination_id": combination_id,
        "campaign_id": campaign_id,
        "intro_gcs_path": intro["gcs_path"],
        "main_gcs_path": main["gcs_path"],
        "output_gcs_path": combo["output_gcs_path"],
        "quality": campaign["quality"],
    })

    logger.info("combination_retried", combination_id=combination_id, campaign_id=campaign_id)
    return {"id": combination_id, "status": "pending"}
