from __future__ import annotations

from uuid import UUID


class DuplicateIdempotencyKey(Exception):
    pass


class IdempotencyConflict(Exception):
    def __init__(self, payment_id: UUID | None = None) -> None:
        self.payment_id = payment_id
        super().__init__("idempotency key already used with a different payload")


class PaymentNotFound(Exception):
    def __init__(self, payment_id: UUID) -> None:
        self.payment_id = payment_id
        super().__init__(f"payment {payment_id} not found")


class TransientDependencyError(Exception):
    pass


class PermanentProcessingError(Exception):
    pass
