from application.outbox.routing import DLQ_ROUTING_KEY, NEW_ROUTING_KEY
from infrastructure.messaging.topology import (
    PAYMENTS_EXCHANGE_NAME,
    DLQ_QUEUE,
    NEW_QUEUE,
    RETRY_QUEUE,
    PaymentsTopology,
)


def test_new_queue_dead_letters_to_dlq() -> None:
    assert NEW_QUEUE.routing_key == NEW_ROUTING_KEY
    assert NEW_QUEUE.arguments is not None
    assert NEW_QUEUE.arguments["x-dead-letter-exchange"] == PAYMENTS_EXCHANGE_NAME
    assert NEW_QUEUE.arguments["x-dead-letter-routing-key"] == DLQ_ROUTING_KEY


def test_retry_queue_dead_letters_back_to_new() -> None:
    assert RETRY_QUEUE.arguments is not None
    assert RETRY_QUEUE.arguments["x-dead-letter-exchange"] == PAYMENTS_EXCHANGE_NAME
    assert RETRY_QUEUE.arguments["x-dead-letter-routing-key"] == NEW_ROUTING_KEY


def test_dlq_has_no_dead_letter_loop() -> None:
    arguments = DLQ_QUEUE.arguments or {}
    assert "x-dead-letter-exchange" not in arguments
    assert "x-dead-letter-routing-key" not in arguments


class _FakeQueue:
    def __init__(self, definition: object) -> None:
        self.definition = definition
        self.binds: list[tuple[object, str]] = []

    async def bind(self, exchange: object, routing_key: str) -> None:
        self.binds.append((exchange, routing_key))


class _FakeBroker:
    def __init__(self) -> None:
        self.exchanges: list[object] = []
        self.queues: list[object] = []
        self.bound: list[_FakeQueue] = []

    async def declare_exchange(self, exchange: object) -> object:
        self.exchanges.append(exchange)
        return exchange

    async def declare_queue(self, queue_def: object) -> _FakeQueue:
        self.queues.append(queue_def)
        bound = _FakeQueue(queue_def)
        self.bound.append(bound)
        return bound


async def test_declare_binds_all_queues() -> None:
    broker = _FakeBroker()
    topology = PaymentsTopology()
    await topology.declare(broker)
    assert broker.exchanges == [topology.exchange]
    assert broker.queues == list(topology.queues)
    assert [item.binds[0][0] for item in broker.bound] == [topology.exchange] * 3
    keys = [item.binds[0][1] for item in broker.bound]
    assert keys == [
        topology.new_queue.routing_key or topology.new_queue.name,
        topology.retry_queue.routing_key or topology.retry_queue.name,
        topology.dlq_queue.routing_key or topology.dlq_queue.name,
    ]
