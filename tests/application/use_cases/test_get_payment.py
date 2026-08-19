from uuid import uuid4

import pytest

from application.exceptions import PaymentNotFound
from application.use_cases.get_payment import GetPayment
from tests.application.fakes import (
    InMemoryStore,
    make_uow_factory,
    pending_payment,
)


def _seed_payment(store: InMemoryStore):
    payment = pending_payment()
    store.payments[payment.id.value] = payment
    store.by_key[payment.idempotency_key.value] = payment.id.value
    return payment


@pytest.mark.asyncio
async def test_returns_payment() -> None:
    store = InMemoryStore()
    payment = _seed_payment(store)
    result = await GetPayment(make_uow_factory(store)).execute(payment.id.value)
    assert result.payment_id == payment.id.value
    assert result.status == "pending"
    assert result.amount == payment.money.amount


@pytest.mark.asyncio
async def test_missing_payment_raises() -> None:
    store = InMemoryStore()
    missing = uuid4()
    with pytest.raises(PaymentNotFound) as exc_info:
        await GetPayment(make_uow_factory(store)).execute(missing)
    assert exc_info.value.payment_id == missing
