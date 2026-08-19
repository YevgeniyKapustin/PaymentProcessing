from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from domain.exceptions import (
    InvalidIdempotencyKeyError,
    InvalidPaymentIdError,
)


@dataclass(frozen=True, slots=True)
class PaymentId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise InvalidPaymentIdError("payment id must be a UUID")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidIdempotencyKeyError("idempotency key must be a non-empty string")
        if len(self.value) > 255:
            raise InvalidIdempotencyKeyError("idempotency key is too long")
