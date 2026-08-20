from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from application.exceptions import DuplicateIdempotencyKey
from application.payments.events import PAYMENT_CREATED
from application.records import GatewayResult, OutboxStatus
from application.uow import UowFactory
from domain.ids import IdempotencyKey, PaymentId
from domain.money import Currency, Money
from domain.payment import Payment, PaymentStatus
from infrastructure.clock import SystemClock
from infrastructure.gateway.random_emulator import RandomPaymentGateway
from infrastructure.gateway.sql_cache import SqlGatewayResultCache
from infrastructure.persistence.db import PostgresDatabase
from infrastructure.persistence.models import Base
from infrastructure.persistence.models.outbox import OutboxModel
from infrastructure.persistence.uow import SqlAlchemyUnitOfWork
from tests.application.fakes import pending_payment

pytestmark = pytest.mark.integration

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://payments:payments@127.0.0.1:5432/payments_test"
)
ADMIN_DATABASE = "payments"
_SKIP_REASON: str | None = None
_DATABASE_READY = False


def _database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _skip_postgres(reason: str) -> None:
    global _SKIP_REASON
    _SKIP_REASON = reason
    pytest.skip(reason)


async def _ensure_database(url: str) -> None:
    global _SKIP_REASON, _DATABASE_READY
    if _SKIP_REASON is not None:
        pytest.skip(_SKIP_REASON)
    if _DATABASE_READY:
        return
    parsed = make_url(url)
    db_name = parsed.database
    if db_name is None or not db_name.isidentifier():
        _skip_postgres("invalid test database name")
    engine = create_async_engine(url, connect_args={"timeout": 2})
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _DATABASE_READY = True
        return
    except (OSError, OperationalError) as exc:
        message = str(exc).lower()
        unreachable = (
            "refused" in message
            or "could not connect" in message
            or "timeout" in message
            or "does not exist" not in message
        )
        if unreachable:
            _skip_postgres(f"Postgres docker container is not reachable: {exc}")
    finally:
        await engine.dispose()
    admin = create_async_engine(
        parsed.set(database=ADMIN_DATABASE),
        isolation_level="AUTOCOMMIT",
        connect_args={"timeout": 2},
    )
    try:
        async with admin.connect() as conn:
            exists = (
                await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": db_name},
                )
            ).scalar()
            if not exists:
                await conn.execute(text(f"CREATE DATABASE {db_name}"))
    except (OSError, OperationalError) as exc:
        _skip_postgres(f"Postgres docker container is not reachable: {exc}")
    finally:
        await admin.dispose()
    _DATABASE_READY = True


def _payment(*, key: str | None = None) -> Payment:
    return Payment.create(
        id=PaymentId(uuid4()),
        money=Money(Decimal("10.00"), Currency.USD),
        description="x",
        metadata={},
        idempotency_key=IdempotencyKey(key or uuid4().hex),
        webhook_url="https://example.com/hook",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = _database_url()
    await _ensure_database(url)
    database = PostgresDatabase(url)
    engine = database.create_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except (OSError, OperationalError) as exc:
        await engine.dispose()
        pytest.skip(f"Postgres docker container is not reachable: {exc}")
    try:
        yield database.create_session_factory(engine)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
def uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> UowFactory:
    return partial(SqlAlchemyUnitOfWork, session_factory)


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_is_mapped(
    uow_factory: UowFactory,
) -> None:
    first = pending_payment()
    second = pending_payment()
    async with uow_factory() as uow:
        await uow.payments.add(first)
        await uow.commit()
    async with uow_factory() as uow:
        with pytest.raises(DuplicateIdempotencyKey):
            await uow.payments.add(second)


@pytest.mark.asyncio
async def test_get_for_update_and_save_in_one_uow(
    uow_factory: UowFactory,
) -> None:
    payment = pending_payment()
    async with uow_factory() as uow:
        await uow.payments.add(payment)
        await uow.commit()
    processed_at = datetime(2026, 1, 2, tzinfo=UTC)
    async with uow_factory() as uow:
        current = await uow.payments.get_for_update(payment.id)
        assert current is not None
        current.succeed(processed_at)
        await uow.payments.save(current)
        await uow.commit()
    async with uow_factory() as uow:
        loaded = await uow.payments.get(payment.id)
    assert loaded is not None
    assert loaded.status is PaymentStatus.SUCCEEDED
    assert loaded.processed_at == processed_at


@pytest.mark.asyncio
async def test_inbox_duplicate_does_not_rollback_payment(
    uow_factory: UowFactory,
) -> None:
    payment = pending_payment()
    message_id = uuid4()
    now = datetime(2026, 1, 2, tzinfo=UTC)
    async with uow_factory() as uow:
        await uow.inbox.add(message_id, now)
        await uow.commit()
    async with uow_factory() as uow:
        await uow.payments.add(payment)
        await uow.inbox.add(message_id, now)
        await uow.commit()
    async with uow_factory() as uow:
        loaded = await uow.payments.get(payment.id)
        assert loaded is not None
        assert await uow.inbox.has_message(message_id)


@pytest.mark.asyncio
async def test_gateway_cache_keeps_first_charge_across_instances(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rolls = iter([0.0, 0.99])
    monkeypatch.setattr(
        "infrastructure.gateway.random_emulator.random.random",
        lambda: next(rolls),
    )
    monkeypatch.setattr(
        "infrastructure.gateway.random_emulator.random.uniform",
        lambda _a, _b: 0.0,
    )
    cache = SqlGatewayResultCache(session_factory, SystemClock())
    payment = pending_payment()
    first = await RandomPaymentGateway(
        min_delay_seconds=0,
        max_delay_seconds=0,
        cache=cache,
    ).charge(payment)
    second = await RandomPaymentGateway(
        min_delay_seconds=0,
        max_delay_seconds=0,
        cache=cache,
    ).charge(payment)
    assert first.is_successful is True
    assert second.is_successful is True
    stored = await cache.get(payment.id.value)
    assert stored == GatewayResult(is_successful=True)


@pytest.mark.asyncio
async def test_payment_lookups_and_missing_rows(
    uow_factory: UowFactory,
) -> None:
    payment = _payment(key="lookup-1")
    async with uow_factory() as uow:
        assert await uow.payments.get(payment.id) is None
        assert await uow.payments.get_for_update(payment.id) is None
        assert await uow.payments.get_by_idempotency_key(payment.idempotency_key) is None
        await uow.payments.add(payment)
        await uow.commit()
    async with uow_factory() as uow:
        loaded = await uow.payments.get_by_idempotency_key(payment.idempotency_key)
        missing = await uow.inbox.has_message(uuid4())
    assert loaded is not None
    assert loaded.id == payment.id
    assert missing is False


@pytest.mark.asyncio
async def test_save_missing_payment_raises(
    uow_factory: UowFactory,
) -> None:
    async with uow_factory() as uow:
        with pytest.raises(RuntimeError, match="missing for save"):
            await uow.payments.save(_payment())


@pytest.mark.asyncio
async def test_duplicate_primary_key_is_not_idempotency(
    uow_factory: UowFactory,
) -> None:
    first = _payment(key="pk-1")
    second = Payment.create(
        id=first.id,
        money=first.money,
        description="y",
        metadata={},
        idempotency_key=IdempotencyKey("pk-2"),
        webhook_url=first.webhook_url,
        created_at=first.created_at,
    )
    async with uow_factory() as uow:
        await uow.payments.add(first)
        await uow.commit()
    async with uow_factory() as uow:
        with pytest.raises(IntegrityError):
            await uow.payments.add(second)


@pytest.mark.asyncio
async def test_exception_rolls_back_uncommitted_payment(
    uow_factory: UowFactory,
) -> None:
    payment = _payment()
    with pytest.raises(RuntimeError, match="boom"):
        async with uow_factory() as uow:
            await uow.payments.add(payment)
            raise RuntimeError("boom")
    async with uow_factory() as uow:
        assert await uow.payments.get(payment.id) is None


@pytest.mark.asyncio
async def test_commit_outside_context_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)
    with pytest.raises(RuntimeError, match="not active"):
        await uow.commit()
    with pytest.raises(RuntimeError, match="not active"):
        await uow.rollback()


@pytest.mark.asyncio
async def test_outbox_claim_publish_and_counts(
    uow_factory: UowFactory,
) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    async with uow_factory() as uow:
        empty = await uow.outbox_queue.claim_batch(
            10,
            now=now,
            stale_before=now - timedelta(seconds=60),
        )
        await uow.outbox_queue.unclaim([])
        await uow.outbox.add(
            event_type=PAYMENT_CREATED,
            payload={"payment_id": "a"},
            created_at=now,
        )
        await uow.commit()
    assert empty == []
    async with uow_factory() as uow:
        claimed = await uow.outbox_queue.claim_batch(
            10,
            now=now,
            stale_before=now - timedelta(seconds=60),
        )
        await uow.commit()
    assert len(claimed) == 1
    assert claimed[0].status is OutboxStatus.PROCESSING
    async with uow_factory() as uow:
        await uow.outbox_queue.unclaim([claimed[0].id])
        await uow.commit()
    async with uow_factory() as uow:
        again = await uow.outbox_queue.claim_batch(
            10,
            now=now,
            stale_before=now - timedelta(seconds=60),
        )
        await uow.outbox_queue.mark_processed(again[0].id, now)
        await uow.commit()
        assert await uow.outbox_queue.count_pending() == 0
        assert await uow.outbox_queue.count_failed() == 0


@pytest.mark.asyncio
async def test_outbox_release_retry_fail_and_purge(
    uow_factory: UowFactory,
) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    later = now + timedelta(hours=1)
    async with uow_factory() as uow:
        await uow.outbox.add(
            event_type=PAYMENT_CREATED,
            payload={"payment_id": "retry"},
            created_at=now,
        )
        await uow.commit()
    async with uow_factory() as uow:
        claimed = await uow.outbox_queue.claim_batch(
            1,
            now=now,
            stale_before=now - timedelta(seconds=60),
        )
        await uow.outbox_queue.release(
            claimed[0].id,
            status=OutboxStatus.NEW,
            retry_count=1,
            available_at=later,
        )
        await uow.commit()
    async with uow_factory() as uow:
        skipped = await uow.outbox_queue.claim_batch(
            1,
            now=now,
            stale_before=now - timedelta(seconds=60),
        )
        due = await uow.outbox_queue.claim_batch(
            1,
            now=later,
            stale_before=later - timedelta(seconds=60),
        )
        await uow.outbox_queue.release(
            due[0].id,
            status=OutboxStatus.FAILED,
            retry_count=8,
            available_at=None,
        )
        await uow.commit()
        assert skipped == []
        assert await uow.outbox_queue.count_failed() == 1
        assert await uow.outbox_queue.count_pending() == 0


@pytest.mark.asyncio
async def test_outbox_reclaims_stale_processing_and_purges(
    session_factory: async_sessionmaker[AsyncSession],
    uow_factory: UowFactory,
) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    stale_at = now - timedelta(minutes=10)
    record_id = uuid4()
    async with session_factory() as session:
        session.add(
            OutboxModel(
                id=record_id,
                event_type=PAYMENT_CREATED,
                payload={"payment_id": "stale"},
                created_at=stale_at,
                published_at=None,
                status=OutboxStatus.PROCESSING,
                retry_count=0,
                claimed_at=stale_at,
                available_at=None,
            )
        )
        session.add(
            OutboxModel(
                id=uuid4(),
                event_type=PAYMENT_CREATED,
                payload={"payment_id": "old"},
                created_at=stale_at,
                published_at=stale_at,
                status=OutboxStatus.PROCESSED,
                retry_count=0,
                claimed_at=None,
                available_at=None,
            )
        )
        await session.commit()
    async with uow_factory() as uow:
        claimed = await uow.outbox_queue.claim_batch(
            10,
            now=now,
            stale_before=now - timedelta(seconds=60),
        )
        await uow.commit()
    assert [row.id for row in claimed] == [record_id]
    async with uow_factory() as uow:
        deleted = await uow.outbox_queue.delete_processed_before(
            now - timedelta(minutes=1),
            10,
        )
        await uow.commit()
    assert deleted == 1


@pytest.mark.asyncio
async def test_gateway_cache_put_if_absent_keeps_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cache = SqlGatewayResultCache(session_factory, SystemClock())
    payment_id = uuid4()
    assert await cache.get(payment_id) is None
    first = await cache.put_if_absent(payment_id, GatewayResult(is_successful=True))
    second = await cache.put_if_absent(payment_id, GatewayResult(is_successful=False))
    assert first == GatewayResult(is_successful=True)
    assert second == GatewayResult(is_successful=True)
    assert await cache.get(payment_id) == GatewayResult(is_successful=True)
