from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from faststream import FastStream
from faststream.rabbit import RabbitBroker

from infrastructure.messaging.topology import PaymentsTopology


class FastStreamAppFactory:
    def __init__(self, topology: PaymentsTopology | None = None) -> None:
        self._topology = topology or PaymentsTopology()

    def create(
        self,
        broker: RabbitBroker,
        *,
        on_startup: Callable[[], Coroutine[Any, Any, None]] | None = None,
        after_shutdown: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> FastStream:
        app = FastStream(broker)
        topology = self._topology

        @app.on_startup
        async def _startup() -> None:
            if on_startup is not None:
                await on_startup()
            else:
                await broker.connect()
                await topology.declare(broker)

        if after_shutdown is not None:

            @app.after_shutdown
            async def _shutdown() -> None:
                await after_shutdown()

        return app
