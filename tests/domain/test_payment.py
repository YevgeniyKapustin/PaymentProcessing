from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.exceptions import (
    IllegalStatusTransitionError,
    InvalidIdempotencyKeyError,
    InvalidMoneyError,
    InvalidPaymentIdError,
)
from domain.ids import IdempotencyKey, PaymentId
from domain.money import Currency, Money
from domain.payment import Payment, PaymentStatus


def test_illegal_status_transition() -> None:
    with pytest.raises(IllegalStatusTransitionError):
        PaymentStatus.SUCCEEDED.require_transition(PaymentStatus.FAILED)
    with pytest.raises(IllegalStatusTransitionError):
        PaymentStatus.FAILED.require_transition(PaymentStatus.PENDING)
    with pytest.raises(IllegalStatusTransitionError):
        PaymentStatus.SUCCEEDED.require_transition(PaymentStatus.PENDING)


def test_money_rejects_float() -> None:
    with pytest.raises(InvalidMoneyError):
        Money(0.1, Currency.USD)  # type: ignore[arg-type]


def test_money_rejects_bool() -> None:
    with pytest.raises(InvalidMoneyError):
        Money(True, Currency.USD)  # type: ignore[arg-type]


def test_money_rejects_excess_scale() -> None:
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("1.001"), Currency.USD)


def test_money_rejects_zero_and_negative() -> None:
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("0.00"), Currency.USD)
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("-1.00"), Currency.USD)


def test_money_accepts_int_amount() -> None:
    money = Money(10, Currency.USD)
    assert money.amount == Decimal("10.00")
    assert money.currency is Currency.USD


def test_money_rejects_non_decimal_text() -> None:
    with pytest.raises(InvalidMoneyError):
        Money("10.00", Currency.USD)  # type: ignore[arg-type]


def test_money_rejects_non_finite() -> None:
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("NaN"), Currency.USD)
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("Infinity"), Currency.USD)


def test_money_equality_and_hash() -> None:
    left = Money(Decimal("10.00"), Currency.USD)
    right = Money(Decimal("10.00"), Currency.USD)
    other = Money(Decimal("11.00"), Currency.USD)
    assert left == right
    assert left != other
    assert left != Decimal("10.00")
    assert hash(left) == hash(right)
    assert len({left, right, other}) == 2


def test_pending_to_succeeded_sets_processed_at() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2026, 1, 2, tzinfo=UTC)
    payment = Payment.create(
        id=PaymentId(uuid4()),
        money=Money(Decimal("10.00"), Currency.USD),
        description="x",
        metadata={},
        idempotency_key=IdempotencyKey("k"),
        webhook_url="https://example.com/h",
        created_at=now,
    )
    payment.succeed(later)
    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.processed_at == later
    payment.fail(datetime(2026, 1, 3, tzinfo=UTC))
    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.processed_at == later


def test_payment_id_must_be_uuid() -> None:
    with pytest.raises(InvalidPaymentIdError):
        PaymentId("not-a-uuid")  # type: ignore[arg-type]


def test_idempotency_key_rejects_empty_and_long() -> None:
    with pytest.raises(InvalidIdempotencyKeyError):
        IdempotencyKey("")
    with pytest.raises(InvalidIdempotencyKeyError):
        IdempotencyKey("   ")
    with pytest.raises(InvalidIdempotencyKeyError):
        IdempotencyKey("x" * 256)
    assert IdempotencyKey("x" * 255).value == "x" * 255
