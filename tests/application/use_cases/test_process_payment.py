from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.exceptions import (
    PermanentProcessingError,
    TransientDependencyError,
)
from application.use_cases.process_payment import ProcessPayment
from domain.payment import Payment, PaymentStatus
from tests.application.fakes import (
    FakeGateway,
    FakeWebhookSender,
    FrozenClock,
    InMemoryStore,
    InMemoryUnitOfWork,
    make_uow_factory,
    pending_payment,
)

CLOCK = FrozenClock(datetime(2026, 1, 3, tzinfo=UTC))


def _seed(store: InMemoryStore, payment: Payment) -> None:
    store.payments[payment.id.value] = payment
    store.by_key[payment.idempotency_key.value] = payment.id.value


def _use_case(
    store: InMemoryStore,
    gateway: FakeGateway,
    webhook: FakeWebhookSender,
) -> ProcessPayment:
    return ProcessPayment(make_uow_factory(store), gateway, webhook, CLOCK)


def make_save_failing_factory(store: InMemoryStore, fail_times: int = 1):
    remaining = fail_times

    def factory() -> InMemoryUnitOfWork:
        nonlocal remaining
        uow = InMemoryUnitOfWork(store)
        original = uow.payments.save

        async def save(payment: Payment) -> None:
            nonlocal remaining
            if remaining > 0:
                remaining -= 1
                raise RuntimeError("save failed")
            await original(payment)

        uow.payments.save = save  # type: ignore[method-assign]
        return uow

    return factory


def make_missing_on_lock_factory(store: InMemoryStore):
    def factory() -> InMemoryUnitOfWork:
        uow = InMemoryUnitOfWork(store)

        async def missing(_payment_id: object) -> None:
            return None

        uow.payments.get_for_update = missing  # type: ignore[method-assign]
        return uow

    return factory


def make_transient_save_factory(store: InMemoryStore):
    def factory() -> InMemoryUnitOfWork:
        uow = InMemoryUnitOfWork(store)

        async def save(_payment: Payment) -> None:
            raise TransientDependencyError("db busy")

        uow.payments.save = save  # type: ignore[method-assign]
        return uow

    return factory


@pytest.mark.asyncio
async def test_already_final_payment_does_not_call_gateway() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    payment.succeed(datetime(2026, 1, 2, tzinfo=UTC))
    _seed(store, payment)
    gateway = FakeGateway()
    webhook = FakeWebhookSender()
    await _use_case(store, gateway, webhook).execute(payment.id.value)
    assert gateway.calls == 0
    assert payment.status is PaymentStatus.SUCCEEDED
    assert len(webhook.calls) == 1
    assert webhook.calls[0][0] == "https://example.com/hook"


@pytest.mark.asyncio
async def test_charge_success_marks_succeeded_and_sends_webhook() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(is_successful=True)
    webhook = FakeWebhookSender()
    await _use_case(store, gateway, webhook).execute(payment.id.value)
    assert gateway.calls == 1
    stored = store.payments[payment.id.value]
    assert stored.status is PaymentStatus.SUCCEEDED
    assert stored.processed_at == CLOCK.now()
    assert webhook.calls[0][1]["status"] == "succeeded"
    assert webhook.calls[0][2] == str(payment.id.value)


@pytest.mark.asyncio
async def test_charge_failure_marks_failed_and_sends_webhook() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(is_successful=False)
    webhook = FakeWebhookSender()
    await _use_case(store, gateway, webhook).execute(payment.id.value)
    assert gateway.calls == 1
    stored = store.payments[payment.id.value]
    assert stored.status is PaymentStatus.FAILED
    assert webhook.calls[0][1]["status"] == "failed"


@pytest.mark.asyncio
async def test_missing_payment_is_permanent() -> None:
    store = InMemoryStore()
    gateway = FakeGateway()
    webhook = FakeWebhookSender()
    with pytest.raises(PermanentProcessingError):
        await _use_case(store, gateway, webhook).execute(uuid4())
    assert gateway.calls == 0
    assert webhook.calls == []


@pytest.mark.asyncio
async def test_gateway_transient_error_is_reraised() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(error=TransientDependencyError("busy"))
    webhook = FakeWebhookSender()
    with pytest.raises(TransientDependencyError):
        await _use_case(store, gateway, webhook).execute(payment.id.value)
    assert store.payments[payment.id.value].status is PaymentStatus.PENDING
    assert webhook.calls == []


@pytest.mark.asyncio
async def test_gateway_permanent_error_is_reraised() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(error=PermanentProcessingError("declined"))
    webhook = FakeWebhookSender()
    with pytest.raises(PermanentProcessingError):
        await _use_case(store, gateway, webhook).execute(payment.id.value)
    assert store.payments[payment.id.value].status is PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_unexpected_gateway_error_becomes_transient() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(error=RuntimeError("boom"))
    webhook = FakeWebhookSender()
    with pytest.raises(TransientDependencyError):
        await _use_case(store, gateway, webhook).execute(payment.id.value)
    assert store.payments[payment.id.value].status is PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_retry_after_save_failure_does_not_capture_twice() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(is_successful=True)
    webhook = FakeWebhookSender()
    use_case = ProcessPayment(
        make_save_failing_factory(store),
        gateway,
        webhook,
        CLOCK,
    )
    with pytest.raises(TransientDependencyError, match="persist"):
        await use_case.execute(payment.id.value)
    assert gateway.captures == 1
    assert store.payments[payment.id.value].status is PaymentStatus.PENDING
    await use_case.execute(payment.id.value)
    assert gateway.captures == 1
    assert gateway.calls == 2
    assert store.payments[payment.id.value].status is PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_webhook_failure_after_persist_does_not_charge_again() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(is_successful=True)
    webhook = FakeWebhookSender(fail_times=1)
    use_case = _use_case(store, gateway, webhook)
    with pytest.raises(TransientDependencyError, match="webhook"):
        await use_case.execute(payment.id.value)
    assert gateway.captures == 1
    assert store.payments[payment.id.value].status is PaymentStatus.SUCCEEDED
    await use_case.execute(payment.id.value)
    assert gateway.captures == 1
    assert gateway.calls == 1
    assert len(webhook.calls) == 2
    assert webhook.calls[1][1]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_payment_missing_on_lock_is_permanent() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(is_successful=True)
    webhook = FakeWebhookSender()
    use_case = ProcessPayment(
        make_missing_on_lock_factory(store),
        gateway,
        webhook,
        CLOCK,
    )
    with pytest.raises(PermanentProcessingError, match="not found"):
        await use_case.execute(payment.id.value)
    assert gateway.calls == 1
    assert webhook.calls == []
    assert store.payments[payment.id.value].status is PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_transient_error_during_complete_is_reraised() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    _seed(store, payment)
    gateway = FakeGateway(is_successful=True)
    webhook = FakeWebhookSender()
    use_case = ProcessPayment(
        make_transient_save_factory(store),
        gateway,
        webhook,
        CLOCK,
    )
    with pytest.raises(TransientDependencyError, match="db busy"):
        await use_case.execute(payment.id.value)
    assert webhook.calls == []
    assert store.payments[payment.id.value].status is PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_duplicate_message_id_skips_processing() -> None:
    store = InMemoryStore()
    payment = pending_payment()
    payment.succeed(datetime(2026, 1, 2, tzinfo=UTC))
    _seed(store, payment)
    message_id = uuid4()
    gateway = FakeGateway()
    webhook = FakeWebhookSender()
    use_case = _use_case(store, gateway, webhook)
    await use_case.execute(payment.id.value, message_id=message_id)
    await use_case.execute(payment.id.value, message_id=message_id)
    assert gateway.calls == 0
    assert len(webhook.calls) == 1
