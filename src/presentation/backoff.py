from __future__ import annotations

from typing import Self

from application.retry.backoff import ExponentialDelay

_ERROR_BACKOFF_MIN = 1.0
_ERROR_BACKOFF_MAX = 30.0


class ExponentialBackoff:
    def __init__(
        self,
        initial: float,
        *,
        cap: float = _ERROR_BACKOFF_MAX,
        jitter: bool = True,
        schedule: ExponentialDelay | None = None,
    ) -> None:
        self._schedule = schedule or ExponentialDelay(
            initial=initial,
            cap=cap,
            jitter=jitter,
        )
        self._failures = 0

    @classmethod
    def for_interval(cls, interval: float, *, jitter: bool = True) -> Self:
        return cls(max(interval, _ERROR_BACKOFF_MIN), jitter=jitter)

    def reset(self) -> None:
        self._failures = 0

    def next_delay(self) -> float:
        self._failures += 1
        return self._schedule.seconds(self._failures)
