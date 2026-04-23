from datetime import datetime, timezone

import structlog
from google.cloud import firestore

logger = structlog.get_logger()


class CampaignStore:
    """Firestore-backed persistence for campaigns, videos, and combinations."""

    def __init__(self, project_id: str, collection_prefix: str = "") -> None:
        self._db = firestore.Client(project=project_id)
        self._prefix = collection_prefix

    def _col(self, name: str) -> str:
        return f"{self._prefix}_{name}" if self._prefix else name

    # ---- Campaigns ----

    def create_campaign(self, campaign_id: str, user_id: str, name: str, quality: dict) -> dict:
        doc = {
            "user_id": user_id,
            "name": name,
            "status": "draft",
            "quality": quality,
            "total_combinations": 0,
            "completed_count": 0,
            "failed_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        self._db.collection(self._col("campaigns")).document(campaign_id).set(doc)
        logger.info("campaign_created", campaign_id=campaign_id)
        return {"id": campaign_id, **doc}

    def get_campaign(self, campaign_id: str) -> dict | None:
        snap = self._db.collection(self._col("campaigns")).document(campaign_id).get()
        if not snap.exists:
            return None
        return {"id": snap.id, **snap.to_dict()}

    def list_campaigns(self, user_id: str) -> list[dict]:
        docs = (
            self._db.collection(self._col("campaigns"))
            .where("user_id", "==", user_id)
            .stream()
        )
        results = [{"id": d.id, **d.to_dict()} for d in docs]
        results.sort(key=lambda c: c.get("created_at", ""), reverse=True)
        return results

    def update_campaign(self, campaign_id: str, **fields: object) -> None:
        self._db.collection(self._col("campaigns")).document(campaign_id).update(fields)

    def start_campaign(self, campaign_id: str, total_combinations: int) -> None:
        self.update_campaign(
            campaign_id,
            status="processing",
            total_combinations=total_combinations,
        )

    def increment_completed(self, campaign_id: str) -> None:
        self._db.collection(self._col("campaigns")).document(campaign_id).update(
            {"completed_count": firestore.Increment(1)}
        )

    def increment_failed(self, campaign_id: str) -> None:
        self._db.collection(self._col("campaigns")).document(campaign_id).update(
            {"failed_count": firestore.Increment(1)}
        )

    def decrement_failed(self, campaign_id: str) -> None:
        self._db.collection(self._col("campaigns")).document(campaign_id).update(
            {"failed_count": firestore.Increment(-1), "status": "processing"}
        )

    def check_campaign_done(self, campaign_id: str) -> bool:
        """Check if all combinations are done and update campaign status if so."""
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return False
        total = campaign["total_combinations"]
        done = campaign["completed_count"] + campaign["failed_count"]
        if done >= total:
            status = "completed" if campaign["failed_count"] == 0 else "failed"
            self.update_campaign(
                campaign_id,
                status=status,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            logger.info("campaign_done", campaign_id=campaign_id, status=status)
            return True
        return False

    def delete_campaign(self, campaign_id: str) -> None:
        self._db.collection(self._col("campaigns")).document(campaign_id).delete()

    # ---- Videos (source assets) ----

    def create_video(
        self,
        video_id: str,
        campaign_id: str,
        user_id: str,
        video_type: str,
        filename: str,
        gcs_path: str,
    ) -> dict:
        doc = {
            "campaign_id": campaign_id,
            "user_id": user_id,
            "type": video_type,
            "filename": filename,
            "gcs_path": gcs_path,
            "size_bytes": None,
            "duration_seconds": None,
            "codec": None,
            "width": None,
            "height": None,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._db.collection(self._col("videos")).document(video_id).set(doc)
        logger.info("video_created", video_id=video_id, type=video_type)
        return {"id": video_id, **doc}

    def get_video(self, video_id: str) -> dict | None:
        snap = self._db.collection(self._col("videos")).document(video_id).get()
        if not snap.exists:
            return None
        return {"id": snap.id, **snap.to_dict()}

    def update_video(self, video_id: str, **fields: object) -> None:
        self._db.collection(self._col("videos")).document(video_id).update(fields)

    def list_videos(self, campaign_id: str, video_type: str | None = None) -> list[dict]:
        query = self._db.collection(self._col("videos")).where("campaign_id", "==", campaign_id)
        if video_type:
            query = query.where("type", "==", video_type)
        return [{"id": d.id, **d.to_dict()} for d in query.stream()]

    # ---- Combinations (outputs) ----

    def create_combination(
        self,
        combination_id: str,
        campaign_id: str,
        intro_video_id: str,
        main_video_id: str,
        output_gcs_path: str,
    ) -> dict:
        doc = {
            "campaign_id": campaign_id,
            "intro_video_id": intro_video_id,
            "main_video_id": main_video_id,
            "status": "pending",
            "output_gcs_path": output_gcs_path,
            "output_size_bytes": None,
            "output_duration": None,
            "error": None,
            "attempts": 0,
            "started_at": None,
            "completed_at": None,
        }
        self._db.collection(self._col("combinations")).document(combination_id).set(doc)
        return {"id": combination_id, **doc}

    def create_combinations_batch(self, combinations: list[dict]) -> int:
        """Batch-write multiple combinations. Returns count written."""
        batch = self._db.batch()
        for combo in combinations:
            ref = self._db.collection(self._col("combinations")).document(combo["id"])
            batch.set(ref, {k: v for k, v in combo.items() if k != "id"})
        batch.commit()
        logger.info("combinations_batch_created", count=len(combinations))
        return len(combinations)

    def get_combination(self, combination_id: str) -> dict | None:
        snap = self._db.collection(self._col("combinations")).document(combination_id).get()
        if not snap.exists:
            return None
        return {"id": snap.id, **snap.to_dict()}

    def update_combination(self, combination_id: str, **fields: object) -> None:
        self._db.collection(self._col("combinations")).document(combination_id).update(fields)

    def set_combination_processing(self, combination_id: str) -> None:
        self.update_combination(
            combination_id,
            status="processing",
            started_at=datetime.now(timezone.utc).isoformat(),
            attempts=firestore.Increment(1),
        )

    def set_combination_completed(
        self, combination_id: str, output_size_bytes: int, output_duration: float
    ) -> None:
        self.update_combination(
            combination_id,
            status="completed",
            output_size_bytes=output_size_bytes,
            output_duration=output_duration,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    def set_combination_failed(self, combination_id: str, error: str) -> None:
        self.update_combination(combination_id, status="failed", error=error)

    def reset_combination_for_retry(self, combination_id: str) -> None:
        self.update_combination(
            combination_id,
            status="pending",
            error=None,
            output_size_bytes=None,
            output_duration=None,
            completed_at=None,
        )

    def list_combinations(
        self, campaign_id: str, status: str | None = None
    ) -> list[dict]:
        query = self._db.collection(self._col("combinations")).where(
            "campaign_id", "==", campaign_id
        )
        if status:
            query = query.where("status", "==", status)
        return [{"id": d.id, **d.to_dict()} for d in query.stream()]
