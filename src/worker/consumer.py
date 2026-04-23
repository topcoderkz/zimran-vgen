"""Pub/Sub pull subscriber for processing merge tasks.

Entry point: python -m src.worker.consumer
"""

import json
import os
import signal
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import structlog
from google.cloud import pubsub_v1

from src.config import get_settings
from src.jobs.store import CampaignStore
from src.observability.logging import setup_logging
from src.observability.metrics import MetricsClient
from src.storage.client import StorageClient
from src.worker.pipeline import process_combination

logger = structlog.get_logger()

_running = True


def _handle_signal(signum: int, frame: object) -> None:
    global _running
    logger.info("shutdown_signal", signal=signum)
    _running = False


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"healthy"}')

    def log_message(self, *args: object) -> None:
        pass  # suppress request logs


def _start_health_server() -> None:
    """Cloud Run requires a listening port. Serve a minimal health endpoint."""
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("health_server_started", port=port)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    _start_health_server()

    settings = get_settings()
    setup_logging(settings.log_level)

    store = CampaignStore(settings.gcp_project_id, settings.firestore_collection_prefix)
    gcs = StorageClient(settings.gcp_project_id)
    metrics = MetricsClient(settings.gcp_project_id)

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(
        settings.gcp_project_id, settings.pubsub_subscription
    )

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        payload = None
        try:
            payload = json.loads(message.data.decode("utf-8"))
            logger.info(
                "message_received",
                combination_id=payload.get("combination_id"),
                campaign_id=payload.get("campaign_id"),
            )
            process_combination(settings, store, gcs, metrics, payload)
            logger.info("message_acked", combination_id=payload.get("combination_id"))
        except Exception as exc:
            logger.error("message_processing_failed", error=str(exc)[:500])
        finally:
            # Always ack to prevent infinite redelivery.
            # Failed combinations are tracked in Firestore;
            # retries should be handled at the application level.
            message.ack()

    streaming_pull = subscriber.subscribe(subscription_path, callback=callback)
    logger.info("worker_started", subscription=subscription_path)

    try:
        streaming_pull.result()
    except Exception:
        streaming_pull.cancel()
        streaming_pull.result()

    logger.info("worker_stopped")


if __name__ == "__main__":
    main()
