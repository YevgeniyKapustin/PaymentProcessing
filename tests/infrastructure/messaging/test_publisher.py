from unittest.mock import AsyncMock

import pytest

from infrastructure.messaging.publisher import FastStreamPublisher
from infrastructure.messaging.topology import PAYMENTS_EXCHANGE


@pytest.mark.asyncio
async def test_publish_forwards_to_broker() -> None:
    broker = AsyncMock()
    publisher = FastStreamPublisher(broker)
    await publisher.publish("payments.new", b"{}", headers={"k": "v"})
    broker.publish.assert_awaited_once_with(
        b"{}",
        exchange=PAYMENTS_EXCHANGE,
        routing_key="payments.new",
        persist=True,
        headers={"k": "v"},
        expiration=None,
        content_type="application/json",
    )
