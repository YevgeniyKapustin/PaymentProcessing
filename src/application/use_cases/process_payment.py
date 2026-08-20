from __future__ import annotations

from uuid import UUID

from application.payments.charge import ChargePayment
from application.payments.deliver_webhook import DeliverWebhook
from application.payments.inbox import ProcessedMessageInbox
from application.payments.webhook_payload import WebhookPayloadBuilder
from application.ports import Clock, PaymentGateway, WebhookSender
from application.uow import UowFactory


class ProcessPayment:
    def __init__(
        self,
        uow_factory: UowFactory,
        gateway: PaymentGateway,
        webhook_sender: WebhookSender,
        clock: Clock,
        payloads: WebhookPayloadBuilder | None = None,
        *,
        charge: ChargePayment | None = None,
        webhook: DeliverWebhook | None = None,
        inbox: ProcessedMessageInbox | None = None,
    ) -> None:
        self._inbox = inbox or ProcessedMessageInbox(uow_factory, clock)
        self._charge = charge or ChargePayment(uow_factory, gateway, clock)
        self._webhook = webhook or DeliverWebhook(webhook_sender, payloads)

    async def execute(
        self,
        payment_id: UUID,
        *,
        message_id: UUID | None = None,
    ) -> None:
        if message_id is not None and await self._inbox.has_seen(message_id):
            return
        payment = await self._charge.execute(payment_id)
        await self._webhook.execute(payment)
        if message_id is not None:
            await self._inbox.remember(message_id)
