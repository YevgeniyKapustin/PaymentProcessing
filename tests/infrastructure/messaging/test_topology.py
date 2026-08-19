from application.outbox.routing import DLQ_ROUTING_KEY, NEW_ROUTING_KEY
from infrastructure.messaging.topology import (
    PAYMENTS_EXCHANGE_NAME,
    DLQ_QUEUE,
    NEW_QUEUE,
    RETRY_QUEUE,
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
