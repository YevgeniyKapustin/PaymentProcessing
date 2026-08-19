from __future__ import annotations


class NullOutboxMetrics:
    def record_published(self, lag_seconds: float) -> None:
        return None

    def record_error(self) -> None:
        return None

    def set_queue_size(self, count: int) -> None:
        return None

    def set_failed_count(self, count: int) -> None:
        return None

    def observe_batch(self, duration_seconds: float) -> None:
        return None
