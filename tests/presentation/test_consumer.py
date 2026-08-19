from unittest.mock import AsyncMock, MagicMock

import pytest

from runtime import Runtime, UseCases
from presentation.consumer import PaymentConsumer
from infrastructure.config import Settings
from infrastructure.resources import Resources


def _runtime() -> Runtime:
    return Runtime(
        settings=Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            rabbitmq_url="amqp://guest:guest@localhost/",
            api_key="test",
        ),
        use_cases=UseCases(
            create_payment=AsyncMock(),
            get_payment=AsyncMock(),
            process_payment=AsyncMock(),
            publish_outbox=AsyncMock(),
        ),
        publisher=AsyncMock(),
        gateway=AsyncMock(),
        clock=AsyncMock(),
        resources=Resources(
            engine=AsyncMock(),
            http_client=AsyncMock(),
            broker=MagicMock(),
        ),
    )


@pytest.mark.asyncio
async def test_start_and_close_delegate_to_runtime() -> None:
    runtime = _runtime()
    runtime.start = AsyncMock()
    runtime.close = AsyncMock()
    consumer = PaymentConsumer(runtime)
    await consumer.start()
    await consumer.close()
    runtime.start.assert_awaited_once()
    runtime.close.assert_awaited_once()


def test_handlers_register_before_faststream_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    runtime = _runtime()

    def mark_subscriber(*args: object, **kwargs: object) -> MagicMock:
        order.append("handlers")
        return MagicMock()

    class FakeAppFactory:
        def create(self, *args: object, **kwargs: object) -> MagicMock:
            order.append("app")
            return MagicMock()

    runtime.resources.broker.subscriber.side_effect = mark_subscriber
    monkeypatch.setattr(
        "presentation.consumer.FastStreamAppFactory",
        FakeAppFactory,
    )
    PaymentConsumer(runtime)
    assert order == ["handlers", "app"]
