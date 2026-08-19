from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from domain.payment import Payment


@dataclass(frozen=True, slots=True)
class CreatePaymentInput:
    amount: Decimal
    currency: str
    description: str
    metadata: dict[str, Any]
    webhook_url: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PaymentOutput:
    payment_id: UUID
    amount: Decimal
    currency: str
    description: str
    metadata: dict[str, Any]
    status: str
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_payment(cls, payment: Payment) -> PaymentOutput:
        return cls(
            payment_id=payment.id.value,
            amount=payment.money.amount,
            currency=payment.money.currency.value,
            description=payment.description,
            metadata=payment.metadata,
            status=payment.status.value,
            idempotency_key=payment.idempotency_key.value,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )
