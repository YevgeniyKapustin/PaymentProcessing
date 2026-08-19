from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from application.exceptions import PermanentProcessingError
from application.outbox.codec import OutboxEventCodec
from application.ports import Publisher
from application.use_cases.process_payment import ProcessPayment
from presentation.amqp.failures import RETRY_COUNT_HEADER, FailureRouter
from presentation.log_context import RequestId, log_context

log = logging.getLogger(__name__)

REQUEST_ID_HEADER = "x-request-id"


class PaymentMessageHandler:
    def __init__(
        self,
        process_payment: ProcessPayment,
        publisher: Publisher,
        *,
        events: OutboxEventCodec | None = None,
        failures: FailureRouter | None = None,
    ) -> None:
        self._process_payment = process_payment
        self._events = events or OutboxEventCodec()
        self._request_ids = RequestId()
        self._failures = failures or FailureRouter(publisher)

    async def handle(
        self,
        body: dict[str, Any],
        headers: Mapping[str, Any] | None,
        raw_body: bytes,
    ) -> None:
        payment_id = body.get("payment_id")
        with log_context(
            request_id=self._request_id(headers),
            payment_id=str(payment_id) if payment_id else None,
        ):
            try:
                parsed_id = self._payment_id(body)
                await self._process_payment.execute(
                    parsed_id,
                    message_id=self._events.outbox_id(body, headers),
                )
                log.info(
                    "payment.processed",
                    extra={"payment_id": str(parsed_id)},
                )
            except Exception as exc:
                await self._failures.route(
                    body=raw_body,
                    headers=headers,
                    retry_count=self._retry_count(headers),
                    error=exc,
                )

    def _payment_id(self, body: dict[str, Any]) -> UUID:
        raw = self._events.payment_id(body)
        if raw is None:
            raise PermanentProcessingError("message missing payment_id")
        try:
            return UUID(raw)
        except ValueError as exc:
            raise PermanentProcessingError("invalid payment_id") from exc

    def _retry_count(self, headers: Mapping[str, Any] | None) -> int:
        raw = (headers or {}).get(RETRY_COUNT_HEADER, 0)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def _request_id(self, headers: Mapping[str, Any] | None) -> str:
        raw = (headers or {}).get(REQUEST_ID_HEADER)
        if raw is None:
            raw = (headers or {}).get("X-Request-ID")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if raw is not None:
            raw = str(raw)
        return self._request_ids.resolve(raw)
