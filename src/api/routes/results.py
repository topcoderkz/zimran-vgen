import structlog
from fastapi import APIRouter, HTTPException, Request

from src.config import Settings
from src.jobs.store import CampaignStore
from src.storage.client import StorageClient

logger = structlog.get_logger()
router = APIRouter(tags=["results"])


@router.get("/api/campaigns/{campaign_id}/results")
def list_results(
    campaign_id: str,
    request: Request,
    status: str | None = None,
) -> list[dict]:
    settings: Settings = request.app.state.settings
    store: CampaignStore = request.app.state.store
    gcs: StorageClient = request.app.state.gcs

    campaign = store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    combinations = store.list_combinations(campaign_id, status=status)

    # Enrich with video names and download URLs
    video_cache: dict[str, dict] = {}
    results = []
    for combo in combinations:
        intro = _get_video_cached(store, combo["intro_video_id"], video_cache)
        main = _get_video_cached(store, combo["main_video_id"], video_cache)

        entry = {
            "id": combo["id"],
            "intro_name": intro["filename"] if intro else "unknown",
            "main_name": main["filename"] if main else "unknown",
            "status": combo["status"],
            "output_size_bytes": combo.get("output_size_bytes"),
            "duration_seconds": combo.get("output_duration"),
            "download_url": None,
        }

        if combo["status"] == "completed" and combo.get("output_gcs_path"):
            entry["download_url"] = gcs.generate_signed_download_url(
                bucket_name=settings.gcs_output_bucket,
                blob_path=combo["output_gcs_path"],
                expiry_minutes=settings.signed_url_expiry_minutes,
            )

        results.append(entry)

    return results


@router.get("/api/download/{combination_id}")
def download_combination(combination_id: str, request: Request) -> dict:
    settings: Settings = request.app.state.settings
    store: CampaignStore = request.app.state.store
    gcs: StorageClient = request.app.state.gcs

    combo = store.get_combination(combination_id)
    if not combo:
        raise HTTPException(status_code=404, detail="Combination not found")
    if combo["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Combination is {combo['status']}, not completed")

    url = gcs.generate_signed_download_url(
        bucket_name=settings.gcs_output_bucket,
        blob_path=combo["output_gcs_path"],
        expiry_minutes=settings.signed_url_expiry_minutes,
    )
    return {"download_url": url}


def _get_video_cached(
    store: CampaignStore, video_id: str, cache: dict[str, dict]
) -> dict | None:
    if video_id not in cache:
        cache[video_id] = store.get_video(video_id)  # type: ignore[assignment]
    return cache.get(video_id)
