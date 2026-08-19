from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OutboxMetricsState:
    published: int = 0
    errors: int = 0
    queue: int = 0
    failed: int = 0
    lag_seconds: float = 0.0
    duration_seconds: float = 0.0


class PrometheusTextRenderer:
    def render(self, state: OutboxMetricsState) -> str:
        return "\n".join(
            [
                "# HELP outbox_queue_size Pending outbox rows (NEW + PROCESSING).",
                "# TYPE outbox_queue_size gauge",
                f"outbox_queue_size {state.queue}",
                "# HELP outbox_failed Outbox rows that exhausted publish retries.",
                "# TYPE outbox_failed gauge",
                f"outbox_failed {state.failed}",
                "# HELP outbox_publish_errors_total Outbox publish failures.",
                "# TYPE outbox_publish_errors_total counter",
                f"outbox_publish_errors_total {state.errors}",
                "# HELP outbox_published_total Successfully published outbox rows.",
                "# TYPE outbox_published_total counter",
                f"outbox_published_total {state.published}",
                "# HELP outbox_lag_seconds Age of the last published outbox row.",
                "# TYPE outbox_lag_seconds gauge",
                f"outbox_lag_seconds {state.lag_seconds}",
                "# HELP outbox_processing_duration_seconds Last batch duration.",
                "# TYPE outbox_processing_duration_seconds gauge",
                f"outbox_processing_duration_seconds {state.duration_seconds}",
                "",
            ]
        )
