from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from application.exceptions import PermanentProcessingError
from application.outbox.codec import OutboxEventCodec
from presentation.amqp.failures import RETRY_COUNT_HEADER
from presentation.log_context import RequestId

REQUEST_ID_HEADER = "x-request-id"


class InboundPaymentMessage:
    def __init__(
        self,
        events: OutboxEventCodec | None = None,
        request_ids: RequestId | None = None,
    ) -> None:
        self._events = events or OutboxEventCodec()
        self._request_ids = request_ids or RequestId()

    def parse_payment_id(self, body: dict[str, Any]) -> UUID:
        raw = self._events.extract_payment_id(body)
        if raw is None:
            raise PermanentProcessingError("message missing payment_id")
        try:
            return UUID(raw)
        except ValueError as exc:
            raise PermanentProcessingError("invalid payment_id") from exc

    def parse_outbox_id(
        self,
        body: dict[str, Any],
        headers: Mapping[str, Any] | None,
    ) -> UUID | None:
        return self._events.extract_outbox_id(body, headers)

    def parse_retry_count(self, headers: Mapping[str, Any] | None) -> int:
        raw = (headers or {}).get(RETRY_COUNT_HEADER, 0)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def parse_request_id(self, headers: Mapping[str, Any] | None) -> str:
        raw = (headers or {}).get(REQUEST_ID_HEADER)
        if raw is None:
            raw = (headers or {}).get("X-Request-ID")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if raw is not None:
            raw = str(raw)
        return self._request_ids.resolve(raw)
