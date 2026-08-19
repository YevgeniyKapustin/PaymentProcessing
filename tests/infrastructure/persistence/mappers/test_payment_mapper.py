from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from domain.ids import IdempotencyKey, PaymentId
from domain.money import Currency, Money
from domain.payment import Payment, PaymentStatus
from infrastructure.persistence.mappers.payment import PaymentMapper


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


def test_apply_payment_copies_terminal_state() -> None:
    payment = _payment()
    mapper = PaymentMapper()
    model = mapper.to_model(payment)
    later = datetime(2026, 1, 2, tzinfo=UTC)
    payment.succeed(later)
    mapper.apply(model, payment)
    assert model.status == PaymentStatus.SUCCEEDED.value
    assert model.processed_at == later
    loaded = mapper.to_domain(model)
    assert loaded.status is PaymentStatus.SUCCEEDED
    assert loaded.processed_at == later
