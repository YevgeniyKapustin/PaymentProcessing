from __future__ import annotations

import logging
from typing import Any

from faststream.rabbit.annotations import RabbitMessage

from application.ports import Publisher
from application.use_cases.process_payment import ProcessPayment
from presentation.amqp.body import encode_message_body
from presentation.amqp.handlers import PaymentMessageHandler

log = logging.getLogger(__name__)


class PaymentMessageDispatcher:
    def __init__(
        self,
        process_payment: ProcessPayment,
        publisher: Publisher,
        *,
        handler: PaymentMessageHandler | None = None,
    ) -> None:
        self._handler = handler or PaymentMessageHandler(
            process_payment,
            publisher,
        )

    async def dispatch(self, body: dict[str, Any], message: RabbitMessage) -> None:
        try:
            await self._handler.handle(
                body,
                message.headers,
                encode_message_body(message.body),
            )
        except Exception:
            log.exception("payment.handler_failed")
            await message.reject(requeue=False)
            return
        await message.ack()
