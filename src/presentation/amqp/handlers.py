from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from application.outbox.codec import OutboxEventCodec
from application.ports import Publisher
from application.use_cases.process_payment import ProcessPayment
from presentation.amqp.failures import FailureRouter
from presentation.amqp.identity import InboundPaymentMessage
from presentation.log_context import log_context

log = logging.getLogger(__name__)


class PaymentMessageHandler:
    def __init__(
        self,
        process_payment: ProcessPayment,
        publisher: Publisher,
        *,
        events: OutboxEventCodec | None = None,
        failures: FailureRouter | None = None,
        message: InboundPaymentMessage | None = None,
    ) -> None:
        self._process_payment = process_payment
        self._message = message or InboundPaymentMessage(events=events)
        self._failures = failures or FailureRouter(publisher)

    async def handle(
        self,
        body: dict[str, Any],
        headers: Mapping[str, Any] | None,
        raw_body: bytes,
    ) -> None:
        payment_id = body.get("payment_id")
        with log_context(
            request_id=self._message.request_id(headers),
            payment_id=str(payment_id) if payment_id else None,
        ):
            try:
                parsed_id = self._message.payment_id(body)
                await self._process_payment.execute(
                    parsed_id,
                    message_id=self._message.outbox_id(body, headers),
                )
                log.info(
                    "payment.processed",
                    extra={"payment_id": str(parsed_id)},
                )
            except Exception as exc:
                await self._failures.route(
                    body=raw_body,
                    headers=headers,
                    retry_count=self._message.retry_count(headers),
                    error=exc,
                )
