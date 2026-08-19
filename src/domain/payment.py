from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from domain.exceptions import IllegalStatusTransitionError
from domain.ids import IdempotencyKey, PaymentId
from domain.money import Money


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    def can_move_to(self, target: PaymentStatus) -> bool:
        return target in _TRANSITIONS[self]

    def require_transition(self, target: PaymentStatus) -> None:
        if not self.can_move_to(target):
            raise IllegalStatusTransitionError(self.value, target.value)


_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset({PaymentStatus.SUCCEEDED, PaymentStatus.FAILED}),
    PaymentStatus.SUCCEEDED: frozenset(),
    PaymentStatus.FAILED: frozenset(),
}

_TERMINAL = frozenset({PaymentStatus.SUCCEEDED, PaymentStatus.FAILED})


class Payment:
    def __init__(
        self,
        *,
        id: PaymentId,
        money: Money,
        description: str,
        metadata: Mapping[str, Any],
        status: PaymentStatus,
        idempotency_key: IdempotencyKey,
        webhook_url: str,
        created_at: datetime,
        processed_at: datetime | None,
    ) -> None:
        self._id = id
        self._money = money
        self._description = description
        self._metadata = dict(metadata)
        self._status = status
        self._idempotency_key = idempotency_key
        self._webhook_url = webhook_url
        self._created_at = created_at
        self._processed_at = processed_at

    @classmethod
    def create(
        cls,
        *,
        id: PaymentId,
        money: Money,
        description: str,
        metadata: Mapping[str, Any],
        idempotency_key: IdempotencyKey,
        webhook_url: str,
        created_at: datetime,
    ) -> Payment:
        return cls(
            id=id,
            money=money,
            description=description,
            metadata=metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
            created_at=created_at,
            processed_at=None,
        )

    @classmethod
    def reconstitute(
        cls,
        *,
        id: PaymentId,
        money: Money,
        description: str,
        metadata: Mapping[str, Any],
        status: PaymentStatus,
        idempotency_key: IdempotencyKey,
        webhook_url: str,
        created_at: datetime,
        processed_at: datetime | None,
    ) -> Payment:
        return cls(
            id=id,
            money=money,
            description=description,
            metadata=metadata,
            status=status,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
            created_at=created_at,
            processed_at=processed_at,
        )

    @property
    def id(self) -> PaymentId:
        return self._id

    @property
    def money(self) -> Money:
        return self._money

    @property
    def description(self) -> str:
        return self._description

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    @property
    def status(self) -> PaymentStatus:
        return self._status

    @property
    def idempotency_key(self) -> IdempotencyKey:
        return self._idempotency_key

    @property
    def webhook_url(self) -> str:
        return self._webhook_url

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def processed_at(self) -> datetime | None:
        return self._processed_at

    @property
    def is_terminal(self) -> bool:
        return self._status in _TERMINAL

    def succeed(self, processed_at: datetime) -> None:
        self._complete(PaymentStatus.SUCCEEDED, processed_at)

    def fail(self, processed_at: datetime) -> None:
        self._complete(PaymentStatus.FAILED, processed_at)

    def matches_create_payload(
        self,
        *,
        money: Money,
        description: str,
        metadata: Mapping[str, Any],
        webhook_url: str,
    ) -> bool:
        return (
            self._money == money
            and self._description == description
            and self._metadata == dict(metadata)
            and self._webhook_url == webhook_url
        )

    def _complete(self, status: PaymentStatus, processed_at: datetime) -> None:
        if self._status in _TERMINAL:
            return
        self._status.require_transition(status)
        self._status = status
        self._processed_at = processed_at
