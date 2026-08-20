from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from runtime import Runtime, UseCases
from presentation.publisher import OutboxPublisher
from infrastructure.config import Settings
from infrastructure.resources import Resources


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        rabbitmq_url="amqp://guest:guest@localhost/",
        api_key="test",
    )


def _runtime() -> Runtime:
    return Runtime(
        settings=_settings(),
        use_cases=UseCases(
            create_payment=AsyncMock(),
            get_payment=AsyncMock(),
            process_payment=AsyncMock(),
            publish_outbox=AsyncMock(),
        ),
        publisher=AsyncMock(),
        resources=Resources(
            engine=AsyncMock(),
            http_client=AsyncMock(),
            broker=AsyncMock(),
        ),
    )


class FakeRelay:
    def __init__(self) -> None:
        self.was_started = False
        self.was_stopped = False

    def start(self) -> None:
        self.was_started = True

    async def stop(self) -> None:
        self.was_stopped = True


@pytest.mark.asyncio
async def test_lifespan_starts_runtime_and_relay() -> None:
    runtime = _runtime()
    runtime.start = AsyncMock()
    runtime.close = AsyncMock()
    relay = FakeRelay()
    publisher = OutboxPublisher(runtime, relay=relay)
    app = SimpleNamespace(state=SimpleNamespace())
    async with publisher.lifespan(app):
        runtime.start.assert_awaited_once()
        assert relay.was_started
    assert relay.was_stopped
    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_releases_runtime_if_relay_stop_fails() -> None:
    runtime = _runtime()
    runtime.close = AsyncMock()
    relay = MagicMock()
    relay.stop = AsyncMock(side_effect=RuntimeError("busy"))
    publisher = OutboxPublisher(runtime, relay=relay)
    with pytest.raises(RuntimeError, match="busy"):
        await publisher.close()
    runtime.close.assert_awaited_once()
