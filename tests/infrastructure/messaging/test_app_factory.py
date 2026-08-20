from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.messaging.consumer import FastStreamAppFactory


@pytest.mark.asyncio
async def test_default_startup_connects_and_declares() -> None:
    broker = MagicMock()
    broker.connect = AsyncMock()
    broker.start = AsyncMock()
    topology = AsyncMock()
    app = FastStreamAppFactory(topology).create(broker)
    await app.start()
    broker.connect.assert_awaited_once()
    topology.declare.assert_awaited_once_with(broker)
    broker.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_custom_startup_replaces_connect_and_declare() -> None:
    broker = MagicMock()
    broker.connect = AsyncMock()
    broker.start = AsyncMock()
    topology = AsyncMock()
    startup = AsyncMock()
    app = FastStreamAppFactory(topology).create(broker, on_startup=startup)
    await app.start()
    startup.assert_awaited_once()
    broker.connect.assert_not_called()
    topology.declare.assert_not_called()


@pytest.mark.asyncio
async def test_after_shutdown_hook_is_called() -> None:
    broker = MagicMock()
    broker.stop = AsyncMock()
    shutdown = AsyncMock()
    app = FastStreamAppFactory().create(broker, after_shutdown=shutdown)
    await app.stop()
    shutdown.assert_awaited_once()
