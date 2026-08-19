from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from application.exceptions import DuplicateIdempotencyKey
from application.records import OutboxRecord, OutboxStatus
from domain.ids import IdempotencyKey, PaymentId
from domain.money import Currency, Money
from domain.payment import Payment


def pending_payment() -> Payment:
    return Payment.create(
        id=PaymentId(uuid4()),
        money=Money(Decimal("10.00"), Currency.USD),
        description="x",
        metadata={},
        idempotency_key=IdempotencyKey("k"),
        webhook_url="https://example.com/hook",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _copy_payment(payment: Payment) -> Payment:
    return Payment.reconstitute(
        id=payment.id,
        money=payment.money,
        description=payment.description,
        metadata=payment.metadata,
        status=payment.status,
        idempotency_key=payment.idempotency_key,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )


class InMemoryStore:
    def __init__(self) -> None:
        self.payments: dict[UUID, Payment] = {}
        self.by_key: dict[str, UUID] = {}
        self.outbox: list[OutboxRecord] = []
        self.inbox: set[UUID] = set()


def make_uow_factory(store: InMemoryStore):
    def factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    return factory


class InMemoryPaymentRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._staged_add: list[Payment] = []
        self._staged_save: list[Payment] = []

    async def add(self, payment: Payment) -> None:
        key = payment.idempotency_key.value
        if key in self._store.by_key:
            raise DuplicateIdempotencyKey
        if any(item.idempotency_key.value == key for item in self._staged_add):
            raise DuplicateIdempotencyKey
        self._staged_add.append(payment)

    async def save(self, payment: Payment) -> None:
        self._staged_save.append(payment)

    async def get(self, payment_id: PaymentId) -> Payment | None:
        for item in reversed(self._staged_save):
            if item.id.value == payment_id.value:
                return item
        for item in self._staged_add:
            if item.id.value == payment_id.value:
                return item
        stored = self._store.payments.get(payment_id.value)
        if stored is None:
            return None
        return _copy_payment(stored)

    async def get_for_update(self, payment_id: PaymentId) -> Payment | None:
        return await self.get(payment_id)

    async def get_by_idempotency_key(self, key: IdempotencyKey) -> Payment | None:
        for item in self._staged_add:
            if item.idempotency_key.value == key.value:
                return item
        payment_id = self._store.by_key.get(key.value)
        if payment_id is None:
            return None
        return _copy_payment(self._store.payments[payment_id])

    def commit(self) -> None:
        for payment in self._staged_add:
            self._store.payments[payment.id.value] = payment
            self._store.by_key[payment.idempotency_key.value] = payment.id.value
        for payment in self._staged_save:
            self._store.payments[payment.id.value] = payment
        self._staged_add.clear()
        self._staged_save.clear()

    def rollback(self) -> None:
        self._staged_add.clear()
        self._staged_save.clear()


class InMemoryOutboxRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._staged: list[OutboxRecord] = []

    async def add(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self._staged.append(
            OutboxRecord(
                id=uuid4(),
                event_type=event_type,
                payload=payload,
                created_at=created_at,
                status=OutboxStatus.NEW,
                retry_count=0,
                published_at=None,
                claimed_at=None,
                available_at=None,
            )
        )

    async def claim_batch(
        self,
        limit: int,
        *,
        now: datetime,
        stale_before: datetime,
    ) -> list[OutboxRecord]:
        claimed: list[OutboxRecord] = []
        for row in sorted(self._store.outbox, key=lambda item: item.created_at):
            if len(claimed) >= limit:
                break
            stale = (
                row.status is OutboxStatus.PROCESSING
                and row.claimed_at is not None
                and row.claimed_at <= stale_before
            )
            due = row.available_at is None or row.available_at <= now
            if (row.status is OutboxStatus.NEW and due) or stale:
                updated = replace(
                    row,
                    status=OutboxStatus.PROCESSING,
                    claimed_at=now,
                    available_at=None,
                )
                self._replace(updated)
                claimed.append(updated)
        return claimed

    async def mark_processed(
        self,
        record_id: UUID,
        published_at: datetime,
    ) -> None:
        for row in self._store.outbox:
            if row.id == record_id:
                self._replace(
                    replace(
                        row,
                        status=OutboxStatus.PROCESSED,
                        published_at=published_at,
                        claimed_at=None,
                        available_at=None,
                    )
                )
                return

    async def release(
        self,
        record_id: UUID,
        *,
        status: OutboxStatus,
        retry_count: int,
        available_at: datetime | None = None,
    ) -> None:
        for row in self._store.outbox:
            if row.id == record_id:
                self._replace(
                    replace(
                        row,
                        status=status,
                        retry_count=retry_count,
                        claimed_at=None,
                        available_at=available_at,
                    )
                )
                return

    async def unclaim(self, ids: list[UUID]) -> None:
        id_set = set(ids)
        self._store.outbox = [
            replace(
                row,
                status=OutboxStatus.NEW,
                claimed_at=None,
                available_at=None,
            )
            if row.id in id_set
            else row
            for row in self._store.outbox
        ]

    async def count_pending(self) -> int:
        return sum(
            1
            for row in self._store.outbox
            if row.status in (OutboxStatus.NEW, OutboxStatus.PROCESSING)
        )

    async def count_failed(self) -> int:
        return sum(1 for row in self._store.outbox if row.status is OutboxStatus.FAILED)

    async def delete_processed_before(
        self,
        cutoff: datetime,
        limit: int,
    ) -> int:
        kept: list[OutboxRecord] = []
        deleted = 0
        for row in self._store.outbox:
            expired = (
                row.status is OutboxStatus.PROCESSED
                and row.published_at is not None
                and row.published_at < cutoff
            )
            if expired and deleted < limit:
                deleted += 1
                continue
            kept.append(row)
        self._store.outbox = kept
        return deleted

    def _replace(self, updated: OutboxRecord) -> None:
        self._store.outbox = [
            updated if row.id == updated.id else row for row in self._store.outbox
        ]

    def commit(self) -> None:
        self._store.outbox.extend(self._staged)
        self._staged.clear()

    def rollback(self) -> None:
        self._staged.clear()


class InMemoryInboxRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._staged: list[UUID] = []

    async def exists(self, message_id: UUID) -> bool:
        return message_id in self._store.inbox or message_id in self._staged

    async def add(self, message_id: UUID, processed_at: datetime) -> None:
        if await self.exists(message_id):
            return
        self._staged.append(message_id)

    def commit(self) -> None:
        self._store.inbox.update(self._staged)
        self._staged.clear()

    def rollback(self) -> None:
        self._staged.clear()


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self.payments = InMemoryPaymentRepository(store)
        self.outbox = InMemoryOutboxRepository(store)
        self.outbox_queue = self.outbox
        self.inbox = InMemoryInboxRepository(store)
        self.committed = False

    async def __aenter__(self) -> InMemoryUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.payments.commit()
        self.outbox.commit()
        self.inbox.commit()
        self.committed = True

    async def rollback(self) -> None:
        self.payments.rollback()
        self.outbox.rollback()
        self.inbox.rollback()
