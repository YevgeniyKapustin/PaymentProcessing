from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from factory import RuntimeFactory
from runtime import Runtime, UseCases
from infrastructure.clock import SystemClock
from infrastructure.config import Settings
from infrastructure.gateway.random_emulator import RandomPaymentGateway
from infrastructure.resources import Resources
from tests.application.fakes import FakeGateway, FrozenClock


def _settings(**overrides: object) -> Settings:
    data = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "rabbitmq_url": "amqp://guest:guest@localhost/",
        "api_key": "test",
    }
    data.update(overrides)
    return Settings(**data)  # type: ignore[arg-type]


def _resources(**overrides: object) -> Resources:
    values: dict[str, object] = {
        "engine": AsyncMock(),
        "http_client": AsyncMock(),
        "broker": AsyncMock(),
    }
    values.update(overrides)
    return Resources(**values)  # type: ignore[arg-type]


def _use_cases(**overrides: object) -> UseCases:
    values: dict[str, object] = {
        "create_payment": AsyncMock(),
        "get_payment": AsyncMock(),
        "process_payment": AsyncMock(),
        "publish_outbox": AsyncMock(),
    }
    values.update(overrides)
    return UseCases(**values)  # type: ignore[arg-type]


def _runtime(**overrides: object) -> Runtime:
    values: dict[str, object] = {
        "settings": _settings(),
        "use_cases": _use_cases(),
        "publisher": AsyncMock(),
        "resources": _resources(),
    }
    values.update(overrides)
    return Runtime(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_factory_uses_injected_clock_and_gateway() -> None:
    clock = FrozenClock(datetime(2026, 8, 19, tzinfo=UTC))
    gateway = FakeGateway()
    runtime = RuntimeFactory(
        settings=_settings(),
        clock=clock,
        gateway=gateway,
    ).build()
    try:
        assert runtime.use_cases.create_payment._clock is clock
        assert runtime.use_cases.process_payment._charge._gateway is gateway
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_factory_defaults_clock_and_gateway() -> None:
    runtime = RuntimeFactory(settings=_settings()).build()
    try:
        assert isinstance(runtime.use_cases.create_payment._clock, SystemClock)
        assert isinstance(
            runtime.use_cases.process_payment._charge._gateway,
            RandomPaymentGateway,
        )
        assert runtime.resources.owns_broker is True
        assert runtime.render_metrics() == runtime.metrics.render()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_factory_can_release_broker_ownership() -> None:
    runtime = RuntimeFactory(settings=_settings(), owns_broker=False).build()
    try:
        assert runtime.resources.owns_broker is False
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_http_client_uses_pool_limits_from_settings() -> None:
    settings = _settings(
        webhook_max_connections=7,
        webhook_max_keepalive=3,
    )
    runtime = RuntimeFactory(settings=settings).build()
    try:
        pool = runtime.resources.http_client._transport._pool
        assert pool._max_connections == 7
        assert pool._max_keepalive_connections == 3
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_close_is_lifo() -> None:
    order: list[str] = []
    http_client = AsyncMock()
    broker = AsyncMock()
    engine = AsyncMock()
    http_client.aclose.side_effect = lambda: order.append("http")
    broker.stop.side_effect = lambda: order.append("broker")
    engine.dispose.side_effect = lambda: order.append("engine")
    runtime = _runtime(
        resources=_resources(
            engine=engine,
            http_client=http_client,
            broker=broker,
        ),
    )
    await runtime.close()
    assert order == ["http", "broker", "engine"]


@pytest.mark.asyncio
async def test_start_connects_and_declares_without_consuming() -> None:
    broker = AsyncMock()
    topology = AsyncMock()
    runtime = _runtime(
        resources=_resources(broker=broker, topology=topology),
    )
    await runtime.start()
    broker.connect.assert_awaited_once()
    topology.declare.assert_awaited_once_with(broker)
    broker.start.assert_not_called()


@pytest.mark.asyncio
async def test_start_after_close_allows_another_close() -> None:
    http_client = AsyncMock()
    broker = AsyncMock()
    engine = AsyncMock()
    runtime = _runtime(
        resources=_resources(
            engine=engine,
            http_client=http_client,
            broker=broker,
            topology=AsyncMock(),
        ),
    )
    await runtime.close()
    await runtime.start()
    await runtime.close()
    assert http_client.aclose.await_count == 2
    assert broker.stop.await_count == 2
    assert engine.dispose.await_count == 2


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    broker = AsyncMock()
    topology = AsyncMock()
    runtime = _runtime(
        resources=_resources(broker=broker, topology=topology),
    )
    await runtime.start()
    await runtime.start()
    broker.connect.assert_awaited_once()
    topology.declare.assert_awaited_once_with(broker)
    broker.start.assert_not_called()


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    http_client = AsyncMock()
    broker = AsyncMock()
    engine = AsyncMock()
    runtime = _runtime(
        resources=_resources(
            engine=engine,
            http_client=http_client,
            broker=broker,
        ),
    )
    await runtime.close()
    await runtime.close()
    http_client.aclose.assert_awaited_once()
    broker.stop.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_without_start_still_releases_resources() -> None:
    http_client = AsyncMock()
    engine = AsyncMock()
    runtime = _runtime(
        resources=_resources(http_client=http_client, engine=engine),
    )
    await runtime.close()
    http_client.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_collects_cleanup_errors() -> None:
    http_client = AsyncMock()
    broker = AsyncMock()
    engine = AsyncMock()
    http_client.aclose.side_effect = RuntimeError("http")
    broker.stop.side_effect = RuntimeError("broker")
    engine.dispose.side_effect = RuntimeError("engine")
    runtime = _runtime(
        resources=_resources(
            engine=engine,
            http_client=http_client,
            broker=broker,
        ),
    )
    with pytest.raises(ExceptionGroup) as caught:
        await runtime.close()
    messages = [str(exc) for exc in caught.value.exceptions]
    assert messages == ["http", "broker", "engine"]


@pytest.mark.asyncio
async def test_faststream_shutdown_does_not_stop_broker() -> None:
    broker = AsyncMock()
    http_client = AsyncMock()
    engine = AsyncMock()
    runtime = _runtime(
        resources=_resources(
            engine=engine,
            http_client=http_client,
            broker=broker,
            owns_broker=False,
        ),
    )
    await runtime.close()
    http_client.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    broker.stop.assert_not_called()


@pytest.mark.asyncio
async def test_runtime_context_manager_starts_and_closes() -> None:
    runtime = RuntimeFactory(settings=_settings()).build()
    close = runtime.close
    runtime.start = AsyncMock()
    runtime.close = AsyncMock()
    try:
        async with runtime as entered:
            assert entered is runtime
            runtime.start.assert_awaited_once()
            runtime.close.assert_not_called()
        runtime.close.assert_awaited_once()
    finally:
        await close()


def test_runtime_default_metrics_text_is_empty() -> None:
    assert _runtime().render_metrics() == ""
