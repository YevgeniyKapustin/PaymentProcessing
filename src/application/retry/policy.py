from __future__ import annotations

from enum import StrEnum

from application.exceptions import PermanentProcessingError
from application.retry.backoff import ExponentialDelay

MAX_ATTEMPTS = 3
RETRY_INITIAL_SECONDS = 1.0
RETRY_CAP_SECONDS = 4.0


class DispatchAction(StrEnum):
    RETRY = "retry"
    DLQ = "dlq"


class RetryPolicy:
    def __init__(
        self,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        delay: ExponentialDelay | None = None,
    ) -> None:
        self._max_attempts = max_attempts
        self._delay = delay or ExponentialDelay(
            initial=RETRY_INITIAL_SECONDS,
            cap=RETRY_CAP_SECONDS,
            use_jitter=False,
        )

    def decide_action(self, retry_count: int, error: BaseException) -> DispatchAction:
        if isinstance(error, PermanentProcessingError):
            return DispatchAction.DLQ
        if retry_count + 1 >= self._max_attempts:
            return DispatchAction.DLQ
        return DispatchAction.RETRY

    def compute_delay_seconds(self, retry_count: int) -> int:
        delay = self._delay.delay_for(max(retry_count, 0) + 1)
        return max(1, int(delay))
