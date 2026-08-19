from __future__ import annotations

import asyncio
import random


class UniformRandomDelay:
    def __init__(self, min_seconds: float, max_seconds: float) -> None:
        self._min_seconds = min_seconds
        self._max_seconds = max_seconds

    async def wait(self) -> None:
        delay = random.uniform(self._min_seconds, self._max_seconds)
        await asyncio.sleep(delay)
