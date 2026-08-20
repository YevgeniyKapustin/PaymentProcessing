from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from application.records import GatewayResult
from domain.ids import IdempotencyKey, PaymentId
from domain.money import Currency, Money
from domain.payment import Payment
from infrastructure.gateway.memory_cache import InMemoryGatewayResultCache
from infrastructure.gateway.random_emulator import RandomPaymentGateway


def _payment() -> Payment:
    return Payment.create(
        id=PaymentId(uuid4()),
        money=Money(Decimal("10.00"), Currency.USD),
        description="x",
        metadata={},
        idempotency_key=IdempotencyKey("k"),
        webhook_url="https://example.com/hook",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_gateway_replays_first_result_for_same_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rolls = iter([0.0, 0.99])
    monkeypatch.setattr(
        "infrastructure.gateway.outcome.random.random",
        lambda: next(rolls),
    )
    monkeypatch.setattr(
        "infrastructure.gateway.delay.random.uniform",
        lambda _a, _b: 0.0,
    )
    gateway = RandomPaymentGateway(
        min_delay_seconds=0,
        max_delay_seconds=0,
        success_rate=0.9,
    )
    payment = _payment()
    other = _payment()
    first = await gateway.charge(payment)
    second = await gateway.charge(payment)
    other_result = await gateway.charge(other)
    assert first.is_successful is True
    assert second is first
    assert other_result.is_successful is False


@pytest.mark.asyncio
async def test_gateway_cache_does_not_overwrite_first_result() -> None:
    cache = InMemoryGatewayResultCache()
    payment_id = uuid4()
    first = await cache.put_if_absent(payment_id, GatewayResult(is_successful=True))
    second = await cache.put_if_absent(payment_id, GatewayResult(is_successful=False))
    assert first.is_successful is True
    assert second is first
