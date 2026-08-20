from __future__ import annotations

from application.ports import OutboxMetrics
from application.uow import UowFactory


class OutboxQueueGauges:
    def __init__(self, uow_factory: UowFactory, metrics: OutboxMetrics) -> None:
        self._uow_factory = uow_factory
        self._metrics = metrics

    async def refresh(self) -> None:
        async with self._uow_factory() as uow:
            pending = await uow.outbox_queue.count_pending()
            failed = await uow.outbox_queue.count_failed()
        self._metrics.set_queue_size(pending)
        self._metrics.set_failed_count(failed)
