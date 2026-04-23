import time
from typing import Any

import structlog

logger = structlog.get_logger()

# Try to import Cloud Monitoring; fall back to log-based metrics when unavailable.
try:
    from google.cloud import monitoring_v3

    _HAS_MONITORING = True
except ImportError:
    _HAS_MONITORING = False


class MetricsClient:
    """Thin wrapper around Cloud Monitoring custom metrics.

    When the monitoring library is not installed (local dev), metrics are
    emitted as structured log lines instead.
    """

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.project_name = f"projects/{project_id}"

        if _HAS_MONITORING:
            self._client = monitoring_v3.MetricServiceClient()
        else:
            self._client = None
            logger.warning("cloud_monitoring_unavailable", fallback="log_based")

    def record(self, metric_type: str, value: int, labels: dict[str, str] | None = None) -> None:
        """Write a single int64 data point to Cloud Monitoring."""
        labels = labels or {}
        full_type = f"custom.googleapis.com/video_merger/{metric_type}"

        if self._client is None:
            logger.info("metric_recorded", metric=full_type, value=value, labels=labels)
            return

        series = monitoring_v3.TimeSeries()
        series.metric.type = full_type
        series.resource.type = "global"
        series.resource.labels["project_id"] = self.project_id

        for k, v in labels.items():
            series.metric.labels[k] = v

        now = time.time()
        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": int(now), "nanos": int((now % 1) * 1e9)},
        )
        point = monitoring_v3.Point(
            interval=interval,
            value={"int64_value": value},
        )
        series.points = [point]

        try:
            self._client.create_time_series(name=self.project_name, time_series=[series])
            logger.debug("metric_sent", metric=full_type, value=value)
        except Exception as exc:
            logger.warning("metric_send_failed", metric=full_type, error=str(exc)[:200])

    def record_processing_time(self, duration_ms: int, status: str = "success") -> None:
        self.record("processing_time_ms", duration_ms, {"status": status})

    def record_video_processed(self, status: str = "success") -> None:
        self.record("videos_processed", 1, {"status": status})

    def record_error(self, error_type: str) -> None:
        self.record("errors", 1, {"error_type": error_type})
