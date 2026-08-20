from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from runtime import Runtime, UseCases
from presentation.api import PaymentApi
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


@pytest.mark.asyncio
async def test_lifespan_starts_and_closes_runtime() -> None:
    runtime = _runtime()
    runtime.start = AsyncMock()
    runtime.close = AsyncMock()
    api = PaymentApi(runtime)
    app = SimpleNamespace(state=SimpleNamespace())
    async with api.lifespan(app):
        runtime.start.assert_awaited_once()
        assert app.state.runtime is runtime
    runtime.close.assert_awaited_once()
