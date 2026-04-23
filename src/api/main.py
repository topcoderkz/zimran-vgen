from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.jobs.store import CampaignStore
from src.observability.logging import setup_logging
from src.observability.metrics import MetricsClient
from src.pubsub.publisher import MergePublisher
from src.storage.client import StorageClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)

    app.state.settings = settings
    app.state.metrics = MetricsClient(settings.gcp_project_id)
    app.state.store = CampaignStore(
        project_id=settings.gcp_project_id,
        collection_prefix=settings.firestore_collection_prefix,
    )
    app.state.gcs = StorageClient(settings.gcp_project_id)
    app.state.publisher = MergePublisher(settings.gcp_project_id, settings.pubsub_topic)
    yield


app = FastAPI(title="VGen API", version="1.0.0", lifespan=lifespan)

cors_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]
if app.state.settings.cors_origins:
    cors_origins.extend(app.state.settings.cors_origins.split(","))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.routes.health import router as health_router  # noqa: E402
from src.api.routes.campaigns import router as campaigns_router  # noqa: E402
from src.api.routes.uploads import router as uploads_router  # noqa: E402
from src.api.routes.results import router as results_router  # noqa: E402

app.include_router(health_router)
app.include_router(campaigns_router)
app.include_router(uploads_router)
app.include_router(results_router)
