from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class Publisher(Protocol):
    async def publish(
        self,
        routing_key: str,
        body: bytes,
        *,
        headers: Mapping[str, Any] | None = None,
        expiration: int | None = None,
    ) -> None: ...
