from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from faststream.rabbit import RabbitBroker, RabbitExchange

from infrastructure.messaging.topology import PAYMENTS_EXCHANGE


class FastStreamPublisher:
    def __init__(
        self,
        broker: RabbitBroker,
        exchange: RabbitExchange | None = None,
    ) -> None:
        self._broker = broker
        self._exchange = exchange or PAYMENTS_EXCHANGE

    async def publish(
        self,
        routing_key: str,
        body: bytes,
        *,
        headers: Mapping[str, Any] | None = None,
        expiration: int | None = None,
    ) -> None:
        await self._broker.publish(
            body,
            exchange=self._exchange,
            routing_key=routing_key,
            persist=True,
            headers=dict(headers) if headers is not None else None,
            expiration=expiration,
            content_type="application/json",
        )
