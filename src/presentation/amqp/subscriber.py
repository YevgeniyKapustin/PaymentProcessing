from __future__ import annotations

from typing import Any

from faststream.rabbit import Channel, RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.annotations import RabbitMessage

from presentation.amqp.dispatcher import PaymentMessageDispatcher


class PaymentQueueSubscriber:
    def __init__(self, dispatcher: PaymentMessageDispatcher) -> None:
        self._dispatcher = dispatcher

    def register(
        self,
        broker: RabbitBroker,
        *,
        queue: RabbitQueue,
        exchange: RabbitExchange,
    ) -> None:
        dispatcher = self._dispatcher

        @broker.subscriber(
            queue,
            exchange,
            no_ack=True,
            channel=Channel(prefetch_count=1),
            retry=False,
        )
        async def handle_payments_new(
            body: dict[str, Any],
            message: RabbitMessage,
        ) -> None:
            await dispatcher.dispatch(body, message)
