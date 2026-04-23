import json

import structlog
from google.cloud import pubsub_v1

logger = structlog.get_logger()


class MergePublisher:
    """Publishes merge task messages to Pub/Sub."""

    def __init__(self, project_id: str, topic_name: str) -> None:
        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(project_id, topic_name)

    def publish_combination(self, combination: dict) -> str:
        """Publish a single merge task. Returns the message ID."""
        data = json.dumps(combination).encode("utf-8")
        future = self._publisher.publish(
            self._topic_path,
            data,
            campaign_id=combination["campaign_id"],
            combination_id=combination["combination_id"],
        )
        message_id = future.result()
        logger.debug(
            "combination_published",
            combination_id=combination["combination_id"],
            message_id=message_id,
        )
        return message_id

    def publish_combinations(self, combinations: list[dict]) -> int:
        """Fan-out: publish one message per combination. Returns count published."""
        futures = []
        for combo in combinations:
            data = json.dumps(combo).encode("utf-8")
            future = self._publisher.publish(
                self._topic_path,
                data,
                campaign_id=combo["campaign_id"],
                combination_id=combo["combination_id"],
            )
            futures.append(future)

        # Wait for all publishes to complete
        for f in futures:
            f.result()

        logger.info(
            "combinations_published",
            count=len(futures),
            campaign_id=combinations[0]["campaign_id"] if combinations else None,
        )
        return len(futures)
