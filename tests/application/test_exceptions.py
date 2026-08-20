from uuid import uuid4

from application.exceptions import (
    ApplicationError,
    DuplicateIdempotencyKey,
    IdempotencyConflict,
    PaymentNotFound,
    PermanentProcessingError,
    ProcessingError,
    TransientDependencyError,
)
from domain.exceptions import DomainError


def test_application_errors_share_a_base() -> None:
    assert issubclass(DuplicateIdempotencyKey, ApplicationError)
    assert issubclass(IdempotencyConflict, ApplicationError)
    assert issubclass(PaymentNotFound, ApplicationError)
    assert issubclass(ProcessingError, ApplicationError)
    assert issubclass(TransientDependencyError, ProcessingError)
    assert issubclass(PermanentProcessingError, ProcessingError)


def test_domain_and_application_errors_are_separate() -> None:
    assert not issubclass(DomainError, ApplicationError)
    assert not issubclass(ApplicationError, DomainError)


def test_payment_not_found_keeps_id() -> None:
    payment_id = uuid4()
    error = PaymentNotFound(payment_id)
    assert error.payment_id == payment_id
    assert str(payment_id) in str(error)
