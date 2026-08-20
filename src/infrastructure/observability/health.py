from __future__ import annotations

from faststream.rabbit import RabbitBroker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class InfrastructureReadiness:
    def __init__(
        self,
        engine: AsyncEngine,
        broker: RabbitBroker,
        *,
        timeout_seconds: float = 1.0,
    ) -> None:
        self._engine = engine
        self._broker = broker
        self._timeout_seconds = timeout_seconds

    async def is_ready(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return bool(await self._broker.ping(self._timeout_seconds))
        except Exception:
            return False
