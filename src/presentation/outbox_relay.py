from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from application.use_cases.publish_outbox import PublishOutbox
from presentation.backoff import ExponentialBackoff
from presentation.worker import WorkerLoop

log = logging.getLogger(__name__)


class OutboxWorker(Protocol):
    def start(self) -> None: ...

    async def stop(self) -> None: ...


class OutboxRelay:
    def __init__(
        self,
        publish_outbox: PublishOutbox,
        *,
        interval: float,
        batch_size: int = 50,
        backoff: ExponentialBackoff | None = None,
    ) -> None:
        self._publish_outbox = publish_outbox
        self._interval = interval
        self._batch_size = batch_size
        self._backoff = backoff or ExponentialBackoff.for_interval(interval)
        self._loop = WorkerLoop()

    def start(self) -> None:
        self._loop.start(self._run)

    async def stop(self) -> None:
        await self._loop.stop()

    async def _run(self) -> None:
        while not self._loop.is_stopped():
            try:
                published = await self._publish_outbox.execute()
            except Exception:
                log.exception("outbox relay failed")
                await self._loop.wait(self._backoff.next_delay())
                continue
            self._backoff.reset()
            if published:
                log.info("outbox.published", extra={"count": published})
            if self._loop.is_stopped():
                return
            if published < self._batch_size:
                await self._loop.wait(self._interval)
            else:
                await asyncio.sleep(0)
