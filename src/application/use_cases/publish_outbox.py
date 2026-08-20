from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any
from uuid import UUID

from application.outbox.codec import OutboxEventCodec
from application.outbox.gauges import OutboxQueueGauges
from application.outbox.metrics import NullOutboxMetrics
from application.outbox.purge import PurgeProcessedOutbox
from application.outbox.routing import NEW_ROUTING_KEY
from application.ports import Clock, OutboxMetrics, Publisher
from application.records import OutboxRecord, OutboxStatus
from application.retry.backoff import ExponentialDelay
from application.uow import UowFactory

log = logging.getLogger(__name__)


class PublishOutbox:
    def __init__(
        self,
        uow_factory: UowFactory,
        publisher: Publisher,
        clock: Clock,
        batch_size: int = 50,
        *,
        max_attempts: int = 8,
        claim_timeout_seconds: float = 60.0,
        retention_days: int = 3,
        retry_initial_seconds: float = 1.0,
        retry_cap_seconds: float = 60.0,
        use_jitter: bool = True,
        metrics: OutboxMetrics | None = None,
        events: OutboxEventCodec | None = None,
        backoff: ExponentialDelay | None = None,
        purge: PurgeProcessedOutbox | None = None,
        gauges: OutboxQueueGauges | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._clock = clock
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._claim_timeout = timedelta(seconds=claim_timeout_seconds)
        self._events = events or OutboxEventCodec()
        self._backoff = backoff or ExponentialDelay(
            initial=retry_initial_seconds,
            cap=retry_cap_seconds,
            use_jitter=use_jitter,
        )
        self._metrics = metrics or NullOutboxMetrics()
        self._purge = purge or PurgeProcessedOutbox(
            uow_factory,
            clock,
            retention_days=retention_days,
            batch_size=batch_size,
        )
        self._gauges = gauges or OutboxQueueGauges(uow_factory, self._metrics)

    async def execute(self) -> int:
        started = time.perf_counter()
        records = await self._claim()
        await self._gauges.refresh()
        if not records:
            await self._purge.execute()
            self._metrics.observe_batch(time.perf_counter() - started)
            return 0
        published = 0
        try:
            for record in records:
                try:
                    await self._deliver(record)
                except Exception:
                    log.exception(
                        "outbox.publish_failed",
                        extra=self._log_fields(record),
                    )
                    self._metrics.record_error()
                    if published == 0:
                        await self._unclaim([item.id for item in records])
                        raise
                    await self._retry_or_fail(record)
                else:
                    published += 1
                    lag = (self._clock.now() - record.created_at).total_seconds()
                    self._metrics.record_published(lag)
        finally:
            self._metrics.observe_batch(time.perf_counter() - started)
            await self._gauges.refresh()
        return published

    async def _claim(self) -> list[OutboxRecord]:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            records = await uow.outbox_queue.claim_batch(
                self._batch_size,
                now=now,
                stale_before=now - self._claim_timeout,
            )
            if records:
                await uow.commit()
            return list(records)

    async def _deliver(self, record: OutboxRecord) -> None:
        await self._publish_one(record)
        await self._mark_processed(record)

    async def _publish_one(self, record: OutboxRecord) -> None:
        body, headers = self._events.encode(record)
        await self._publisher.publish(NEW_ROUTING_KEY, body, headers=headers)

    async def _mark_processed(self, record: OutboxRecord) -> None:
        async with self._uow_factory() as uow:
            await uow.outbox_queue.mark_processed(record.id, self._clock.now())
            await uow.commit()

    async def _retry_or_fail(self, record: OutboxRecord) -> None:
        attempts = record.retry_count + 1
        now = self._clock.now()
        if attempts >= self._max_attempts:
            status = OutboxStatus.FAILED
            available_at = None
            log.warning(
                "outbox.permanently_failed",
                extra=self._log_fields(record, attempts),
            )
        else:
            status = OutboxStatus.NEW
            delay = self._backoff.delay_for(attempts)
            available_at = now + timedelta(seconds=delay)
        async with self._uow_factory() as uow:
            await uow.outbox_queue.release(
                record.id,
                status=status,
                retry_count=attempts,
                available_at=available_at,
            )
            await uow.commit()

    async def _unclaim(self, ids: list[UUID]) -> None:
        if not ids:
            return
        async with self._uow_factory() as uow:
            await uow.outbox_queue.unclaim(ids)
            await uow.commit()

    def _log_fields(
        self,
        record: OutboxRecord,
        retry_count: int | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "outbox_id": str(record.id),
            "event_type": record.event_type,
            "payment_id": record.payload.get("payment_id"),
        }
        if retry_count is not None:
            fields["retry_count"] = retry_count
        return fields
