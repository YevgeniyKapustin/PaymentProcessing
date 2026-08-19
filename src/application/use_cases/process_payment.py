from __future__ import annotations

from uuid import UUID

from application.exceptions import (
    PermanentProcessingError,
    TransientDependencyError,
)
from application.ports import Clock, PaymentGateway, WebhookSender
from application.records import GatewayResult
from application.uow import UowFactory
from application.payments.webhook_payload import WebhookPayloadBuilder
from domain.ids import PaymentId
from domain.payment import Payment


class ProcessPayment:
    def __init__(
        self,
        uow_factory: UowFactory,
        gateway: PaymentGateway,
        webhook_sender: WebhookSender,
        clock: Clock,
        payloads: WebhookPayloadBuilder | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._webhook_sender = webhook_sender
        self._clock = clock
        self._payloads = payloads or WebhookPayloadBuilder()

    async def execute(
        self,
        payment_id: UUID,
        *,
        message_id: UUID | None = None,
    ) -> None:
        if message_id is not None and await self._seen(message_id):
            return
        payment = await self._load(payment_id)
        if not payment.is_terminal:
            await self._charge_and_complete(payment)
            payment = await self._load(payment_id)
        payload = self._payloads.build(payment)
        await self._webhook_sender.send(
            payment.webhook_url,
            payload,
            idempotency_key=str(payment.id.value),
        )
        if message_id is not None:
            await self._remember(message_id)

    async def _seen(self, message_id: UUID) -> bool:
        async with self._uow_factory() as uow:
            return await uow.inbox.exists(message_id)

    async def _remember(self, message_id: UUID) -> None:
        async with self._uow_factory() as uow:
            await uow.inbox.add(message_id, self._clock.now())
            await uow.commit()

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
                    raise PermanentProcessingError(f"payment {payment.id.value} not found")
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
