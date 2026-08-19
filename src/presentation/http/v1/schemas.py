from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from application.payments.dto import CreatePaymentInput
from domain.money import Currency


class CreatePaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    currency: Currency
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl

    def to_input(self, idempotency_key: str) -> CreatePaymentInput:
        return CreatePaymentInput(
            amount=self.amount,
            currency=self.currency.value,
            description=self.description,
            metadata=self.metadata,
            webhook_url=str(self.webhook_url),
            idempotency_key=idempotency_key,
        )


class CreatePaymentResponse(BaseModel):
    payment_id: UUID
    status: str
    created_at: datetime


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
