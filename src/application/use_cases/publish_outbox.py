from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any
from uuid import UUID

from application.outbox.codec import OutboxEventCodec
from application.outbox.metrics import NullOutboxMetrics
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
        jitter: bool = True,
        metrics: OutboxMetrics | None = None,
        events: OutboxEventCodec | None = None,
        backoff: ExponentialDelay | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._clock = clock
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._claim_timeout = timedelta(seconds=claim_timeout_seconds)
        self._retention_days = retention_days
        self._events = events or OutboxEventCodec()
        self._backoff = backoff or ExponentialDelay(
            initial=retry_initial_seconds,
            cap=retry_cap_seconds,
            jitter=jitter,
        )
        self._metrics = metrics or NullOutboxMetrics()

    async def execute(self) -> int:
        started = time.perf_counter()
        records = await self._claim()
        await self._refresh_gauges()
        if not records:
            await self._purge()
            self._metrics.observe_batch(time.perf_counter() - started)
            return 0
        published = 0
        try:
            for record in records:
                try:
                    await self._publish_one(record)
                    await self._mark_processed(record)
                    published += 1
                    lag = (self._clock.now() - record.created_at).total_seconds()
                    self._metrics.record_published(lag)
                except Exception:
                    log.exception("outbox.publish_failed", extra=self._log_fields(record))
                    self._metrics.record_error()
                    if published == 0:
                        await self._unclaim([item.id for item in records])
                        raise
                    await self._retry_or_fail(record)
        finally:
            self._metrics.observe_batch(time.perf_counter() - started)
            await self._refresh_gauges()
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
            delay = self._backoff.seconds(attempts)
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

    async def _refresh_gauges(self) -> None:
        async with self._uow_factory() as uow:
            pending = await uow.outbox_queue.count_pending()
            failed = await uow.outbox_queue.count_failed()
        self._metrics.set_queue_size(pending)
        self._metrics.set_failed_count(failed)

    async def _purge(self) -> None:
        cutoff = self._clock.now() - timedelta(days=self._retention_days)
        async with self._uow_factory() as uow:
            await uow.outbox_queue.delete_processed_before(cutoff, self._batch_size)
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
