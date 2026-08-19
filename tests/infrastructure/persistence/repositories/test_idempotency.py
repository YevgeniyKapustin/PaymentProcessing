from sqlalchemy.exc import IntegrityError

from infrastructure.persistence.repositories.idempotency import IdempotencyConstraint


class _Orig:
    def __init__(self, constraint_name: str, message: str) -> None:
        self.constraint_name = constraint_name
        self._message = message

    def __str__(self) -> str:
        return self._message


def test_idempotency_constraint_is_detected() -> None:
    orig = _Orig("uq_payments_idempotency_key", "duplicate key")
    assert IdempotencyConstraint().matches(IntegrityError("INSERT", {}, orig))


def test_other_unique_constraint_is_not_idempotency() -> None:
    orig = _Orig("payments_pkey", "duplicate key value violates unique constraint")
    assert not IdempotencyConstraint().matches(IntegrityError("INSERT", {}, orig))


def test_message_fallback_detects_idempotency_key() -> None:
    orig = _Orig("", "duplicate key value on column idempotency_key")
    assert IdempotencyConstraint().matches(IntegrityError("INSERT", {}, orig))
