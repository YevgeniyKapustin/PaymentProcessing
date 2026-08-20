from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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


class ProcessingError(Exception):
    pass


class TransientDependencyError(ProcessingError):
    pass


class PermanentProcessingError(ProcessingError):
    pass


@contextmanager
def wrap_as_transient(message: str) -> Iterator[None]:
    try:
        yield
    except ProcessingError:
        raise
    except Exception as exc:
        raise TransientDependencyError(message) from exc
