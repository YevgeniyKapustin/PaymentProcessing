from __future__ import annotations

import random


class ExponentialDelay:
    def __init__(
        self,
        *,
        initial: float,
        cap: float,
        jitter: bool = True,
    ) -> None:
        self._initial = initial
        self._cap = cap
        self._jitter = jitter

    def seconds(self, attempts: int) -> float:
        if attempts < 1:
            return 0.0
        delay = min(self._initial * (2 ** (attempts - 1)), self._cap)
        if not self._jitter:
            return delay
        return delay * (0.5 + random.random() * 0.5)
