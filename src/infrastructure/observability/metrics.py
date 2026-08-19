from __future__ import annotations

from infrastructure.observability.prometheus import (
    OutboxMetricsState,
    PrometheusTextRenderer,
)


class PrometheusOutboxMetrics:
    def __init__(self, renderer: PrometheusTextRenderer | None = None) -> None:
        self._state = OutboxMetricsState()
        self._renderer = renderer or PrometheusTextRenderer()

    def record_published(self, lag_seconds: float) -> None:
        self._state.published += 1
        self._state.lag_seconds = lag_seconds

    def record_error(self) -> None:
        self._state.errors += 1

    def set_queue_size(self, count: int) -> None:
        self._state.queue = count

    def set_failed_count(self, count: int) -> None:
        self._state.failed = count

    def observe_batch(self, duration_seconds: float) -> None:
        self._state.duration_seconds = duration_seconds

    def render(self) -> str:
        return self._renderer.render(self._state)
