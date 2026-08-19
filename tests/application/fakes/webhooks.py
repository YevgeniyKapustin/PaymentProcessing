from __future__ import annotations

from typing import Any

from application.exceptions import TransientDependencyError


class FakeWebhookSender:
    def __init__(
        self,
        *,
        fail_times: int = 0,
        error: BaseException | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any], str]] = []
        self._fail_times = fail_times
        self._error = error or TransientDependencyError("webhook failed")

    async def send(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> None:
        self.calls.append((url, payload, idempotency_key))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._error
