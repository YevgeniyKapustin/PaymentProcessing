from datetime import UTC, datetime
from decimal import Decimal

import pytest

from application.payments.dto import CreatePaymentInput
from application.payments.events import PAYMENT_CREATED
from application.exceptions import (
    DuplicateIdempotencyKey,
    IdempotencyConflict,
)
from application.use_cases.create_payment import CreatePayment
from domain.exceptions import InvalidCurrencyError, InvalidWebhookUrlError
from domain.ids import IdempotencyKey
from domain.payment import Payment
from tests.application.fakes import (
    FrozenClock,
    InMemoryStore,
    InMemoryUnitOfWork,
    make_uow_factory,
)


def _use_case(store: InMemoryStore) -> CreatePayment:
    clock = FrozenClock(datetime(2026, 8, 18, tzinfo=UTC))
    return CreatePayment(make_uow_factory(store), clock)


def _command(**overrides: object) -> CreatePaymentInput:
    data = {
        "amount": Decimal("10.00"),
        "currency": "USD",
        "description": "coffee",
        "metadata": {"order": "1"},
        "webhook_url": "https://example.com/hook",
        "idempotency_key": "same-key",
    }
    data.update(overrides)
    return CreatePaymentInput(**data)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_same_key_same_body_returns_same_id() -> None:
    store = InMemoryStore()
    use_case = _use_case(store)
    first = await use_case.execute(_command())
    second = await use_case.execute(_command())
    assert first.payment_id == second.payment_id
    assert len(store.payments) == 1
    assert len(store.outbox) == 1


@pytest.mark.asyncio
async def test_same_key_different_body_conflicts() -> None:
    store = InMemoryStore()
    use_case = _use_case(store)
    await use_case.execute(_command())
    with pytest.raises(IdempotencyConflict):
        await use_case.execute(_command(amount=Decimal("20.00")))


@pytest.mark.asyncio
async def test_payment_and_outbox_appear_together() -> None:
    store = InMemoryStore()
    use_case = _use_case(store)
    result = await use_case.execute(_command())
    assert result.payment_id in store.payments
    assert len(store.outbox) == 1
    assert store.outbox[0].payload["payment_id"] == str(result.payment_id)
    assert store.outbox[0].event_type == PAYMENT_CREATED


@pytest.mark.asyncio
async def test_unsupported_currency_is_domain_error() -> None:
    with pytest.raises(InvalidCurrencyError):
        await _use_case(InMemoryStore()).execute(_command(currency="GBP"))


@pytest.mark.asyncio
async def test_private_webhook_url_is_domain_error() -> None:
    with pytest.raises(InvalidWebhookUrlError):
        await _use_case(InMemoryStore()).execute(
            _command(webhook_url="http://127.0.0.1/hook"),
        )


def _duplicate_missing_factory(store: InMemoryStore):
    def factory() -> InMemoryUnitOfWork:
        uow = InMemoryUnitOfWork(store)

        async def add(_payment: Payment) -> None:
            raise DuplicateIdempotencyKey

        async def get_by_key(_key: IdempotencyKey) -> Payment | None:
            return None

        uow.payments.add = add  # type: ignore[method-assign]
        uow.payments.get_by_idempotency_key = get_by_key  # type: ignore[method-assign]
        return uow

    return factory


@pytest.mark.asyncio
async def test_duplicate_key_without_existing_is_conflict() -> None:
    store = InMemoryStore()
    clock = FrozenClock(datetime(2026, 8, 18, tzinfo=UTC))
    use_case = CreatePayment(_duplicate_missing_factory(store), clock)
    with pytest.raises(IdempotencyConflict) as exc_info:
        await use_case.execute(_command())
    assert exc_info.value.payment_id is None
    assert not isinstance(exc_info.value, DuplicateIdempotencyKey)
