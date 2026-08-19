from __future__ import annotations


class DomainError(Exception):
    pass


class InvalidMoneyError(DomainError):
    pass


class InvalidCurrencyError(DomainError):
    pass


class InvalidIdempotencyKeyError(DomainError):
    pass


class InvalidPaymentIdError(DomainError):
    pass


class IllegalStatusTransitionError(DomainError):
    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"cannot transition from {current} to {target}")
