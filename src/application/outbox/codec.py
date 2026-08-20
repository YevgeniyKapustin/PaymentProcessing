from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from application.records import OutboxRecord

EVENT_VERSION = 1
OUTBOX_ID_HEADER = "x-outbox-id"
EVENT_TYPE_HEADER = "x-event-type"


class OutboxEventCodec:
    def encode(self, record: OutboxRecord) -> tuple[bytes, dict[str, str]]:
        body = {
            "outbox_id": str(record.id),
            "event_type": record.event_type,
            "event_version": EVENT_VERSION,
            "payload": record.payload,
        }
        headers = {
            OUTBOX_ID_HEADER: str(record.id),
            EVENT_TYPE_HEADER: record.event_type,
        }
        return json.dumps(body).encode("utf-8"), headers

    def extract_payment_id(self, body: dict[str, Any]) -> str | None:
        payload = body.get("payload")
        if isinstance(payload, dict) and payload.get("payment_id") is not None:
            return self._to_text(payload.get("payment_id"))
        return self._to_text(body.get("payment_id"))

    def extract_outbox_id(
        self,
        body: dict[str, Any],
        headers: Mapping[str, Any] | None,
    ) -> UUID | None:
        raw = body.get("outbox_id")
        if raw is None and headers is not None:
            raw = headers.get(OUTBOX_ID_HEADER)
        text = self._to_text(raw)
        if text is None:
            return None
        try:
            return UUID(text)
        except ValueError:
            return None

    def _to_text(self, raw: object) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        text = str(raw).strip()
        return text or None
