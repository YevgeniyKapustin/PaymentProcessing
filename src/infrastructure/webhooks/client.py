from __future__ import annotations

import httpx


class HttpxWebhookClientFactory:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_connections: int,
        max_keepalive: int,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_connections = max_connections
        self._max_keepalive = max_keepalive

    def create(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout_seconds),
            limits=httpx.Limits(
                max_connections=self._max_connections,
                max_keepalive_connections=self._max_keepalive,
            ),
            follow_redirects=False,
        )
