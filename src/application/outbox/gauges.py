from __future__ import annotations

from application.ports import OutboxMetrics
from application.uow import UowFactory


class OutboxQueueGauges:
    def __init__(self, uow_factory: UowFactory, metrics: OutboxMetrics) -> None:
        self._uow_factory = uow_factory
        self._metrics = metrics

    async def refresh(self) -> None:
        async with self._uow_factory() as uow:
            pending_count = await uow.outbox_queue.count_pending()
            failed_count = await uow.outbox_queue.count_failed()
        self._metrics.set_queue_size(pending_count)
        self._metrics.set_failed_count(failed_count)
