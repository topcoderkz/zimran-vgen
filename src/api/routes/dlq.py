"""Dead-letter queue inspection endpoints."""

import json

import structlog
from fastapi import APIRouter, HTTPException, Request
from google.cloud import pubsub_v1

logger = structlog.get_logger()

router = APIRouter(prefix="/api/dlq", tags=["dlq"])


@router.get("/messages")
def list_dlq_messages(request: Request, limit: int = 10):
    """Pull up to `limit` messages from the DLQ without acknowledging them.

    Messages remain in the subscription and will be redelivered.
    Use POST /api/dlq/purge to dismiss a message after review.
    """
    settings = request.app.state.settings
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(
        settings.gcp_project_id, settings.pubsub_dlq_subscription
    )

    response = subscriber.pull(
        request={"subscription": subscription_path, "max_messages": min(limit, 25)},
        timeout=5,
    )

    messages = []
    for msg in response.received_messages:
        try:
            data = json.loads(msg.message.data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = msg.message.data.decode("utf-8", errors="replace")

        messages.append({
            "ack_id": msg.ack_id,
            "message_id": msg.message.message_id,
            "publish_time": msg.message.publish_time.isoformat() if msg.message.publish_time else None,
            "delivery_attempt": msg.delivery_attempt,
            "attributes": dict(msg.message.attributes),
            "data": data,
        })

    # Modify ack deadline to 0 so messages are immediately available again
    if response.received_messages:
        ack_ids = [m.ack_id for m in response.received_messages]
        subscriber.modify_ack_deadline(
            request={
                "subscription": subscription_path,
                "ack_ids": ack_ids,
                "ack_deadline_seconds": 0,
            }
        )

    logger.info("dlq_messages_listed", count=len(messages))
    return {"count": len(messages), "messages": messages}


@router.post("/purge/{message_id}")
def purge_dlq_message(request: Request, message_id: str):
    """Acknowledge (dismiss) a specific DLQ message by re-pulling and matching.

    This removes the message from the DLQ permanently.
    """
    settings = request.app.state.settings
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(
        settings.gcp_project_id, settings.pubsub_dlq_subscription
    )

    response = subscriber.pull(
        request={"subscription": subscription_path, "max_messages": 100},
        timeout=5,
    )

    target_ack_id = None
    other_ack_ids = []
    for msg in response.received_messages:
        if msg.message.message_id == message_id:
            target_ack_id = msg.ack_id
        else:
            other_ack_ids.append(msg.ack_id)

    if not target_ack_id:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found in DLQ")

    # Ack the target message (permanently removes it)
    subscriber.acknowledge(
        request={"subscription": subscription_path, "ack_ids": [target_ack_id]}
    )

    # Release other messages back immediately
    if other_ack_ids:
        subscriber.modify_ack_deadline(
            request={
                "subscription": subscription_path,
                "ack_ids": other_ack_ids,
                "ack_deadline_seconds": 0,
            }
        )

    logger.info("dlq_message_purged", message_id=message_id)
    return {"purged": message_id}
