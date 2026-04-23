from datetime import datetime, timezone

from fastapi import APIRouter, Request

from src.config import Settings

router = APIRouter()


@router.get("/api/health")
def health(request: Request) -> dict:
    settings: Settings = request.app.state.settings
    return {
        "status": "healthy",
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
