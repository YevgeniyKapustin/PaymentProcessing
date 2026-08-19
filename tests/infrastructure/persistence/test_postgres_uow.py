from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import partial
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.exceptions import DuplicateIdempotencyKey
from application.records import GatewayResult
from application.uow import UowFactory
from domain.payment import PaymentStatus
from infrastructure.clock import SystemClock
from infrastructure.gateway.random_emulator import RandomPaymentGateway
from infrastructure.gateway.sql_cache import SqlGatewayResultCache
from infrastructure.persistence.db import PostgresDatabase
from infrastructure.persistence.models import Base
from infrastructure.persistence.uow import SqlAlchemyUnitOfWork
from tests.application.fakes import pending_payment

pytestmark = pytest.mark.integration


def _database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database = PostgresDatabase(_database_url())
    engine = database.create_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
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
        assert await uow.inbox.exists(message_id)


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
    assert first.succeeded is True
    assert second.succeeded is True
    stored = await cache.get(payment.id.value)
    assert stored == GatewayResult(succeeded=True)
