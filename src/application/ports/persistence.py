from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, Self
from uuid import UUID

from application.records import OutboxRecord, OutboxStatus
from domain.ids import IdempotencyKey, PaymentId
from domain.payment import Payment


class PaymentRepository(Protocol):
    async def add(self, payment: Payment) -> None: ...

    async def save(self, payment: Payment) -> None: ...

    async def get(self, payment_id: PaymentId) -> Payment | None: ...

    async def get_for_update(self, payment_id: PaymentId) -> Payment | None: ...

    async def get_by_idempotency_key(
        self,
        key: IdempotencyKey,
    ) -> Payment | None: ...


class OutboxWriter(Protocol):
    async def add(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> None: ...


class OutboxQueue(Protocol):
    async def claim_batch(
        self,
        limit: int,
        *,
        now: datetime,
        stale_before: datetime,
    ) -> Sequence[OutboxRecord]: ...

    async def mark_processed(
        self,
        record_id: UUID,
        published_at: datetime,
    ) -> None: ...

    async def release(
        self,
        record_id: UUID,
        *,
        status: OutboxStatus,
        retry_count: int,
        available_at: datetime | None = None,
    ) -> None: ...

    async def unclaim(self, ids: Sequence[UUID]) -> None: ...

    async def count_pending(self) -> int: ...

    async def count_failed(self) -> int: ...

    async def delete_processed_before(
        self,
        cutoff: datetime,
        limit: int,
    ) -> int: ...


class InboxRepository(Protocol):
    async def has_message(self, message_id: UUID) -> bool: ...

    async def add(self, message_id: UUID, processed_at: datetime) -> None: ...


class UnitOfWork(Protocol):
    payments: PaymentRepository
    outbox: OutboxWriter
    outbox_queue: OutboxQueue
    inbox: InboxRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
