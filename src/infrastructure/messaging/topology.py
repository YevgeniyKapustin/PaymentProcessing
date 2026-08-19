from __future__ import annotations

from typing import Protocol

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from application.outbox.routing import (
    DLQ_ROUTING_KEY,
    NEW_ROUTING_KEY,
    RETRY_ROUTING_KEY,
)

PAYMENTS_EXCHANGE_NAME = "payments"
NEW_QUEUE_NAME = NEW_ROUTING_KEY
RETRY_QUEUE_NAME = RETRY_ROUTING_KEY
DLQ_NAME = DLQ_ROUTING_KEY

PAYMENTS_EXCHANGE = RabbitExchange(
    PAYMENTS_EXCHANGE_NAME,
    type=ExchangeType.DIRECT,
    durable=True,
)

NEW_QUEUE = RabbitQueue(
    NEW_QUEUE_NAME,
    durable=True,
    routing_key=NEW_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": PAYMENTS_EXCHANGE_NAME,
        "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
    },
)

RETRY_QUEUE = RabbitQueue(
    RETRY_QUEUE_NAME,
    durable=True,
    routing_key=RETRY_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": PAYMENTS_EXCHANGE_NAME,
        "x-dead-letter-routing-key": NEW_ROUTING_KEY,
    },
)

DLQ_QUEUE = RabbitQueue(
    DLQ_NAME,
    durable=True,
    routing_key=DLQ_ROUTING_KEY,
)


class MessageBrokerTopology(Protocol):
    async def declare(self, broker: RabbitBroker) -> None: ...


class PaymentsTopology:
    exchange = PAYMENTS_EXCHANGE
    new_queue = NEW_QUEUE
    retry_queue = RETRY_QUEUE
    dlq_queue = DLQ_QUEUE
    queues = (NEW_QUEUE, RETRY_QUEUE, DLQ_QUEUE)

    async def declare(self, broker: RabbitBroker) -> None:
        exchange = await broker.declare_exchange(self.exchange)
        for queue_def in self.queues:
            queue = await broker.declare_queue(queue_def)
            routing_key = queue_def.routing_key or queue_def.name
            await queue.bind(exchange, routing_key=routing_key)
