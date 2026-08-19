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

    async def dispatch(self, body: dict[str, Any], msg: RabbitMessage) -> None:
        try:
            await self._handler.handle(
                body,
                msg.headers,
                encode_message_body(msg.body),
            )
        except Exception:
            log.exception("payment.handler_failed")
            await msg.reject(requeue=False)
            return
        await msg.ack()
