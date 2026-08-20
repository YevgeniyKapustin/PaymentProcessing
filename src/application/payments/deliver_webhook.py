from __future__ import annotations

from application.payments.webhook_payload import WebhookPayloadBuilder
from application.ports import WebhookSender
from domain.payment import Payment


class DeliverWebhook:
    def __init__(
        self,
        sender: WebhookSender,
        payloads: WebhookPayloadBuilder | None = None,
    ) -> None:
        self._sender = sender
        self._payloads = payloads or WebhookPayloadBuilder()

    async def execute(self, payment: Payment) -> None:
        payload = self._payloads.build(payment)
        await self._sender.send(
            payment.webhook_url,
            payload,
            idempotency_key=str(payment.id.value),
        )
