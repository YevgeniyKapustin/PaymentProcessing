from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class FakePublisher:
    def __init__(
        self,
        error: BaseException | None = None,
        fail_on: int | None = None,
    ) -> None:
        self.error = error
        self.fail_on = fail_on
        self.calls = 0
        self.messages: list[tuple[str, bytes, dict[str, Any] | None, int | None]] = []

    async def publish(
        self,
        routing_key: str,
        body: bytes,
        *,
        headers: Mapping[str, Any] | None = None,
        expiration: int | None = None,
    ) -> None:
        self.calls += 1
        if self.error is not None and (self.fail_on is None or self.calls == self.fail_on):
            raise self.error
        stored = dict(headers) if headers is not None else None
        self.messages.append((routing_key, body, stored, expiration))
