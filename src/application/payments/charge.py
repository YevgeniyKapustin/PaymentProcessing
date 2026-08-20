from __future__ import annotations

from uuid import UUID

from application.exceptions import (
    PermanentProcessingError,
    TransientDependencyError,
)
from application.ports import Clock, PaymentGateway
from application.records import GatewayResult
from application.uow import UowFactory
from domain.ids import PaymentId
from domain.payment import Payment


class ChargePayment:
    def __init__(
        self,
        uow_factory: UowFactory,
        gateway: PaymentGateway,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._clock = clock

    async def execute(self, payment_id: UUID) -> Payment:
        payment = await self._load(payment_id)
        if not payment.is_terminal:
            await self._charge_and_complete(payment)
            payment = await self._load(payment_id)
        return payment

    async def _load(self, payment_id: UUID) -> Payment:
        async with self._uow_factory() as uow:
            payment = await uow.payments.get(PaymentId(payment_id))
            if payment is None:
                raise PermanentProcessingError(f"payment {payment_id} not found")
            return payment

    async def _charge_and_complete(self, payment: Payment) -> None:
        result = await self._charge(payment)
        await self._complete(payment, result)

    async def _charge(self, payment: Payment) -> GatewayResult:
        try:
            return await self._gateway.charge(payment)
        except TransientDependencyError:
            raise
        except PermanentProcessingError:
            raise
        except Exception as exc:
            raise TransientDependencyError("gateway call failed") from exc

    async def _complete(self, payment: Payment, result: GatewayResult) -> None:
        try:
            async with self._uow_factory() as uow:
                current = await uow.payments.get_for_update(payment.id)
                if current is None:
                    raise PermanentProcessingError(
                        f"payment {payment.id.value} not found",
                    )
                if not current.is_terminal:
                    now = self._clock.now()
                    if result.succeeded:
                        current.succeed(now)
                    else:
                        current.fail(now)
                    await uow.payments.save(current)
                    await uow.commit()
        except PermanentProcessingError:
            raise
        except TransientDependencyError:
            raise
        except Exception as exc:
            raise TransientDependencyError("failed to persist payment") from exc
