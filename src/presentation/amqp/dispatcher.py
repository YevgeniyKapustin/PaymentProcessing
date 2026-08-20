from __future__ import annotations

import logging
from typing import Any

from faststream.rabbit.annotations import RabbitMessage

from application.ports import Publisher
from application.use_cases.process_payment import ProcessPayment
from presentation.amqp.body import encode_message_body
from presentation.amqp.failures import FailureRouter
from presentation.amqp.handlers import PaymentMessageHandler
from presentation.amqp.identity import InboundPaymentMessage

log = logging.getLogger(__name__)


class PaymentMessageDispatcher:
    def __init__(
        self,
        process_payment: ProcessPayment,
        publisher: Publisher,
        *,
        handler: PaymentMessageHandler | None = None,
        failures: FailureRouter | None = None,
        message: InboundPaymentMessage | None = None,
    ) -> None:
        identity = message or InboundPaymentMessage()
        self._handler = handler or PaymentMessageHandler(
            process_payment,
            message=identity,
        )
        self._failures = failures or FailureRouter(publisher)
        self._message = identity

    async def dispatch(self, body: dict[str, Any], message: RabbitMessage) -> None:
        raw_body = encode_message_body(message.body)
        try:
            await self._handler.handle(body, message.headers)
        except Exception as exc:
            await self._route_failure(raw_body, message, exc)
        else:
            await message.ack()

    async def _route_failure(
        self,
        raw_body: bytes,
        message: RabbitMessage,
        error: Exception,
    ) -> None:
        try:
            await self._failures.route(
                body=raw_body,
                headers=message.headers,
                retry_count=self._message.parse_retry_count(message.headers),
                error=error,
            )
        except Exception:
            log.exception("payment.handler_failed")
            await message.reject(requeue=False)
        else:
            await message.ack()
