from __future__ import annotations

from uuid import UUID

from application.payments.dto import PaymentOutput
from application.exceptions import PaymentNotFound
from application.uow import UowFactory
from domain.ids import PaymentId


class GetPayment:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, payment_id: UUID) -> PaymentOutput:
        async with self._uow_factory() as uow:
            payment = await uow.payments.get(PaymentId(payment_id))
            if payment is None:
                raise PaymentNotFound(payment_id)
            return PaymentOutput.from_payment(payment)
