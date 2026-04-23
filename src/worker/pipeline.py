import os
import shutil
import tempfile
import time

import structlog

from src.config import Settings
from src.jobs.store import CampaignStore
from src.observability.metrics import MetricsClient
from src.storage.client import StorageClient
from src.video.merger import merge_videos, merge_videos_reencode
from src.video.validator import check_compatibility, validate_video

logger = structlog.get_logger()


def process_combination(
    settings: Settings,
    store: CampaignStore,
    gcs: StorageClient,
    metrics: MetricsClient,
    message: dict,
) -> None:
    """Full merge pipeline: download -> merge -> upload -> update Firestore.

    Args:
        message: Pub/Sub payload with keys: combination_id, campaign_id,
                 intro_gcs_path, main_gcs_path, output_gcs_path, quality.
    """
    combination_id = message["combination_id"]
    campaign_id = message["campaign_id"]

    store.set_combination_processing(combination_id)
    start = time.monotonic()
    tmpdir = tempfile.mkdtemp(prefix="vgen_")

    try:
        intro_local = os.path.join(tmpdir, "intro.mp4")
        main_local = os.path.join(tmpdir, "main.mp4")
        output_local = os.path.join(tmpdir, "output.mp4")

        # Download from GCS
        logger.info("pipeline_downloading", combination_id=combination_id)
        gcs.download_to_file(settings.gcs_upload_bucket, message["intro_gcs_path"], intro_local)
        gcs.download_to_file(settings.gcs_upload_bucket, message["main_gcs_path"], main_local)

        # Merge
        quality = message.get("quality", {})
        codec = quality.get("codec", "copy")

        compatible, reason = check_compatibility(intro_local, main_local)
        if compatible and codec == "copy":
            logger.info("pipeline_merging", combination_id=combination_id, method="stream_copy")
            merge_videos(intro_local, main_local, output_local)
        else:
            logger.info(
                "pipeline_merging",
                combination_id=combination_id,
                method="reencode",
                reason=reason if not compatible else f"codec={codec}",
            )
            merge_videos_reencode(intro_local, main_local, output_local)

        # Validate
        meta = validate_video(output_local)

        # Upload to GCS
        logger.info("pipeline_uploading", combination_id=combination_id)
        gcs.upload_from_file(settings.gcs_output_bucket, message["output_gcs_path"], output_local)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Update Firestore
        store.set_combination_completed(
            combination_id,
            output_size_bytes=meta["size_bytes"],
            output_duration=meta["duration_seconds"],
        )
        store.increment_completed(campaign_id)
        store.check_campaign_done(campaign_id)

        metrics.record_video_processed("success")
        metrics.record_processing_time(elapsed_ms, "success")
        logger.info("pipeline_complete", combination_id=combination_id, elapsed_ms=elapsed_ms)

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        store.set_combination_failed(combination_id, error=str(exc)[:500])
        store.increment_failed(campaign_id)
        store.check_campaign_done(campaign_id)

        metrics.record_video_processed("failure")
        metrics.record_error(type(exc).__name__)
        logger.error("pipeline_failed", combination_id=combination_id, error=str(exc)[:500])
        raise

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
