from __future__ import annotations

from uuid import uuid4

from application.payments.dto import CreatePaymentInput, PaymentOutput
from application.payments.events import PAYMENT_CREATED
from application.exceptions import (
    DuplicateIdempotencyKey,
    IdempotencyConflict,
)
from application.ports import Clock
from application.uow import UowFactory
from domain.ids import IdempotencyKey, PaymentId
from domain.money import Money
from domain.payment import Payment
from domain.webhook import WebhookUrl


def has_matching_create_input(
    payment: Payment,
    command: CreatePaymentInput,
    money: Money,
) -> bool:
    return (
        payment.money == money
        and payment.description == command.description
        and payment.metadata == command.metadata
        and payment.webhook_url == command.webhook_url
    )


class CreatePayment:
    def __init__(self, uow_factory: UowFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, command: CreatePaymentInput) -> PaymentOutput:
        money = Money(command.amount, command.currency)
        key = IdempotencyKey(command.idempotency_key)
        webhook_url = WebhookUrl(command.webhook_url).value
        now = self._clock.now()
        payment = Payment.create(
            id=PaymentId(uuid4()),
            money=money,
            description=command.description,
            metadata=command.metadata,
            idempotency_key=key,
            webhook_url=webhook_url,
            created_at=now,
        )
        try:
            async with self._uow_factory() as uow:
                await uow.payments.add(payment)
                await uow.outbox.add(
                    event_type=PAYMENT_CREATED,
                    payload={"payment_id": str(payment.id.value)},
                    created_at=now,
                )
                await uow.commit()
        except DuplicateIdempotencyKey:
            return await self._replay_existing(command, money, key)
        else:
            return PaymentOutput.from_payment(payment)

    async def _replay_existing(
        self,
        command: CreatePaymentInput,
        money: Money,
        key: IdempotencyKey,
    ) -> PaymentOutput:
        async with self._uow_factory() as uow:
            existing = await uow.payments.get_by_idempotency_key(key)
        if existing is None:
            raise IdempotencyConflict() from None
        if not has_matching_create_input(existing, command, money):
            raise IdempotencyConflict(existing.id.value) from None
        return PaymentOutput.from_payment(existing)
