from __future__ import annotations

import ast
import json
import logging
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from application.exceptions import TransientDependencyError
from application.outbox.routing import DLQ_ROUTING_KEY, RETRY_ROUTING_KEY
from application.use_cases.process_payment import ProcessPayment
from infrastructure.messaging.topology import NEW_QUEUE, PAYMENTS_EXCHANGE
from presentation.amqp.body import encode_message_body
from presentation.amqp.dispatcher import PaymentMessageDispatcher
from presentation.amqp.failures import RETRY_COUNT_HEADER
from presentation.amqp.handlers import PaymentMessageHandler
from presentation.amqp.subscriber import PaymentQueueSubscriber
from tests.application.fakes import (
    FakeGateway,
    FakePublisher,
    FakeWebhookSender,
    FrozenClock,
    InMemoryStore,
    make_uow_factory,
    pending_payment,
)

CLOCK = FrozenClock(datetime(2026, 1, 3, tzinfo=UTC))


def _process(
    store: InMemoryStore,
    gateway: FakeGateway | None = None,
) -> ProcessPayment:
    return ProcessPayment(
        make_uow_factory(store),
        gateway or FakeGateway(),
        FakeWebhookSender(),
        CLOCK,
    )


def _raw(body: dict) -> bytes:
    return json.dumps(body).encode("utf-8")


async def _handle(
    body: dict,
    headers: dict | None,
    raw: bytes,
    *,
    store: InMemoryStore | None = None,
    gateway: FakeGateway | None = None,
    publisher: FakePublisher | None = None,
) -> FakePublisher:
    used_publisher = publisher or FakePublisher()
    handler = PaymentMessageHandler(
        _process(store or InMemoryStore(), gateway),
        used_publisher,
    )
    await handler.handle(body, headers, raw)
    return used_publisher


@pytest.mark.asyncio
async def test_envelope_payload_payment_id_is_processed() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payload": {"payment_id": str(payment.id.value)}}
    publisher = await _handle(body, {}, _raw(body), store=store)
    assert publisher.messages == []
    assert store.payments[payment.id.value].is_terminal


@pytest.mark.asyncio
async def test_missing_payment_id_goes_to_dlq() -> None:
    publisher = await _handle({}, None, b"{}")
    routing, payload, headers, _expiration = publisher.messages[0]
    assert routing == DLQ_ROUTING_KEY
    assert payload == b"{}"
    assert headers is None


@pytest.mark.asyncio
async def test_invalid_payment_id_goes_to_dlq() -> None:
    publisher = await _handle({"payment_id": "not-a-uuid"}, None, b"{}")
    assert publisher.messages[0][0] == DLQ_ROUTING_KEY


def test_raw_body_encodes_dict_and_bytes() -> None:
    assert encode_message_body(b"abc") == b"abc"
    assert json.loads(encode_message_body({"a": 1})) == {"a": 1}
    assert encode_message_body(bytearray(b"xy")) == b"xy"
    assert encode_message_body(memoryview(b"ab")) == b"ab"
    with pytest.raises(TypeError, match="unsupported message body"):
        encode_message_body("raw")


def _amqp_source(name: str) -> Path:
    return Path(__file__).resolve().parents[3] / "src" / "presentation" / "amqp" / name


def test_amqp_adapters_do_not_import_infrastructure() -> None:
    for name in (
        "body.py",
        "dispatcher.py",
        "failures.py",
        "handlers.py",
        "identity.py",
        "subscriber.py",
    ):
        tree = ast.parse(_amqp_source(name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("infrastructure")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("infrastructure")


def test_register_requires_injected_topology() -> None:
    params = signature(PaymentQueueSubscriber.register).parameters
    assert "queue" in params
    assert "exchange" in params


@pytest.mark.asyncio
async def test_success_does_not_republish() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    publisher = await _handle(
        {"payment_id": str(payment.id.value)},
        {},
        _raw({"payment_id": str(payment.id.value)}),
        store=store,
    )
    assert publisher.messages == []


@pytest.mark.asyncio
async def test_bytes_request_id_header_is_decoded() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payment_id": str(payment.id.value)}
    publisher = await _handle(
        body,
        {"x-request-id": b"amqp-bytes"},
        _raw(body),
        store=store,
    )
    assert publisher.messages == []
    assert store.payments[payment.id.value].is_terminal


@pytest.mark.asyncio
async def test_subscriber_dispatches_to_handler() -> None:
    captured: dict[str, object] = {}

    def fake_subscriber(*args: object, **kwargs: object):
        def decorator(fn):
            captured["handler"] = fn
            return fn

        return decorator

    class FakeBroker:
        subscriber = staticmethod(fake_subscriber)

    dispatcher = AsyncMock()
    PaymentQueueSubscriber(dispatcher).register(
        FakeBroker(),
        queue=NEW_QUEUE,
        exchange=PAYMENTS_EXCHANGE,
    )
    msg = object()
    handler = captured["handler"]
    assert callable(handler)
    await handler({"payment_id": "x"}, msg)
    dispatcher.dispatch.assert_awaited_once_with({"payment_id": "x"}, msg)


@pytest.mark.asyncio
async def test_success_logs_processed(caplog: pytest.LogCaptureFixture) -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payment_id": str(payment.id.value)}
    with caplog.at_level(logging.INFO):
        await _handle(body, {"x-request-id": "amqp-1"}, _raw(body), store=store)
    records = [item for item in caplog.records if item.message == "payment.processed"]
    assert records
    assert records[-1].payment_id == str(payment.id.value)


@pytest.mark.asyncio
async def test_transient_error_schedules_retry() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payment_id": str(payment.id.value)}
    publisher = await _handle(
        body,
        {},
        _raw(body),
        store=store,
        gateway=FakeGateway(error=TransientDependencyError("busy")),
    )
    routing, payload, headers, expiration = publisher.messages[0]
    assert routing == RETRY_ROUTING_KEY
    assert payload == _raw(body)
    assert headers is not None
    assert headers[RETRY_COUNT_HEADER] == 1
    assert expiration == 1


@pytest.mark.asyncio
async def test_invalid_retry_count_starts_from_zero() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payment_id": str(payment.id.value)}
    publisher = await _handle(
        body,
        {RETRY_COUNT_HEADER: "x"},
        _raw(body),
        store=store,
        gateway=FakeGateway(error=TransientDependencyError("busy")),
    )
    routing, _payload, headers, expiration = publisher.messages[0]
    assert routing == RETRY_ROUTING_KEY
    assert headers is not None
    assert headers[RETRY_COUNT_HEADER] == 1
    assert expiration == 1


@pytest.mark.asyncio
async def test_second_retry_uses_two_second_ttl() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payment_id": str(payment.id.value)}
    publisher = await _handle(
        body,
        {RETRY_COUNT_HEADER: 1},
        _raw(body),
        store=store,
        gateway=FakeGateway(error=TransientDependencyError("busy")),
    )
    routing, _payload, headers, expiration = publisher.messages[0]
    assert routing == RETRY_ROUTING_KEY
    assert headers is not None
    assert headers[RETRY_COUNT_HEADER] == 2
    assert expiration == 2


@pytest.mark.asyncio
async def test_exhausted_retries_go_to_dlq() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payment_id": str(payment.id.value)}
    raw = _raw(body)
    publisher = await _handle(
        body,
        {RETRY_COUNT_HEADER: 2},
        raw,
        store=store,
        gateway=FakeGateway(error=TransientDependencyError("busy")),
    )
    routing, payload, headers, expiration = publisher.messages[0]
    assert routing == DLQ_ROUTING_KEY
    assert payload == raw
    assert headers == {RETRY_COUNT_HEADER: 2}
    assert expiration is None


@pytest.mark.asyncio
async def test_unknown_payment_goes_to_dlq() -> None:
    body = {"payment_id": str(uuid4())}
    publisher = await _handle(body, {}, _raw(body))
    assert publisher.messages[0][0] == DLQ_ROUTING_KEY


@pytest.mark.asyncio
async def test_envelope_message_is_deduped_on_retry() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    store.by_key[payment.idempotency_key.value] = payment.id.value
    outbox_id = uuid4()
    body = {
        "outbox_id": str(outbox_id),
        "event_type": "PaymentCreated",
        "event_version": 1,
        "payload": {"payment_id": str(payment.id.value)},
    }
    handler = PaymentMessageHandler(_process(store), FakePublisher())
    await handler.handle(body, {"x-outbox-id": str(outbox_id)}, _raw(body))
    await handler.handle(body, {"x-outbox-id": str(outbox_id)}, _raw(body))
    stored = store.payments[payment.id.value]
    assert stored.is_terminal
    assert outbox_id in store.inbox


class _FakeMessage:
    def __init__(self, body: bytes, headers: dict | None = None) -> None:
        self.body = body
        self.headers = headers or {}
        self.acked = False
        self.requeue: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, requeue: bool = False) -> None:
        self.requeue = requeue


@pytest.mark.asyncio
async def test_dispatch_acks_after_success() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    body = {"payment_id": str(payment.id.value)}
    msg = _FakeMessage(_raw(body), {})
    dispatcher = PaymentMessageDispatcher(_process(store), FakePublisher())
    await dispatcher.dispatch(body, msg)
    assert msg.acked is True
    assert msg.requeue is None


@pytest.mark.asyncio
async def test_dispatch_rejects_to_dlq_when_forward_fails() -> None:
    msg = _FakeMessage(b"{}", {})
    dispatcher = PaymentMessageDispatcher(
        _process(InMemoryStore()),
        FakePublisher(error=RuntimeError("broker down")),
    )
    await dispatcher.dispatch({}, msg)
    assert msg.acked is False
    assert msg.requeue is False
