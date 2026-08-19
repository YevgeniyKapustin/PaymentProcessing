from __future__ import annotations

from typing import Any

import httpx

from infrastructure.webhooks.errors import WebhookErrorMapper


class HttpxWebhookSender:
    def __init__(
        self,
        client: httpx.AsyncClient,
        errors: WebhookErrorMapper | None = None,
    ) -> None:
        self._client = client
        self._errors = errors or WebhookErrorMapper()

    async def send(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> None:
        try:
            response = await self._client.post(
                url,
                json=payload,
                headers={"Idempotency-Key": idempotency_key},
            )
        except httpx.TimeoutException as exc:
            raise self._errors.timeout() from exc
        except httpx.TransportError as exc:
            raise self._errors.transport() from exc
        self._errors.from_status(response.status_code)
