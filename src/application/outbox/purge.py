from __future__ import annotations

from datetime import timedelta

from application.ports import Clock
from application.uow import UowFactory


class PurgeProcessedOutbox:
    def __init__(
        self,
        uow_factory: UowFactory,
        clock: Clock,
        *,
        retention_days: int,
        batch_size: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._retention_days = retention_days
        self._batch_size = batch_size

    async def execute(self) -> None:
        cutoff = self._clock.now() - timedelta(days=self._retention_days)
        async with self._uow_factory() as uow:
            await uow.outbox_queue.delete_processed_before(
                cutoff,
                self._batch_size,
            )
            await uow.commit()
