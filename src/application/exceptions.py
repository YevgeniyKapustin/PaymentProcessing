from __future__ import annotations

from uuid import UUID


class ApplicationError(Exception):
    pass


class DuplicateIdempotencyKey(ApplicationError):
    pass


class IdempotencyConflict(ApplicationError):
    def __init__(self, payment_id: UUID | None = None) -> None:
        self.payment_id = payment_id
        super().__init__("idempotency key already used with a different payload")


class PaymentNotFound(ApplicationError):
    def __init__(self, payment_id: UUID) -> None:
        self.payment_id = payment_id
        super().__init__(f"payment {payment_id} not found")


class ProcessingError(ApplicationError):
    pass


class TransientDependencyError(ProcessingError):
    pass


class PermanentProcessingError(ProcessingError):
    pass
