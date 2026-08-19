from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine

from infrastructure.messaging.topology import (
    MessageBrokerTopology,
    PaymentsTopology,
)

Cleanup = Callable[[], Awaitable[object]]


class ResourceCleanup:
    async def run(self, steps: list[Cleanup]) -> list[Exception]:
        errors: list[Exception] = []
        for step in steps:
            try:
                await step()
            except Exception as exc:
                errors.append(exc)
        return errors


@dataclass
class Resources:
    engine: AsyncEngine
    http_client: httpx.AsyncClient
    broker: RabbitBroker
    owns_broker: bool = True
    topology: MessageBrokerTopology = field(default_factory=PaymentsTopology)
    cleanup: ResourceCleanup = field(default_factory=ResourceCleanup)
    _started: bool = field(default=False, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        if self._started:
            return
        self._closed = False
        await self.broker.connect()
        await self.topology.declare(self.broker)
        self._started = True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        errors = await self.cleanup.run(self._shutdown_steps())
        self._started = False
        if errors:
            raise ExceptionGroup(
                "Failed to gracefully shutdown resources",
                errors,
            )

    def _shutdown_steps(self) -> list[Cleanup]:
        steps: list[Cleanup] = [self.http_client.aclose]
        if self.owns_broker:
            steps.append(self.broker.stop)
        steps.append(self.engine.dispose)
        return steps
