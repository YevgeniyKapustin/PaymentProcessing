from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Self

from fastapi import FastAPI

from runtime import Runtime
from presentation.base import Entrypoint
from presentation.outbox_relay import OutboxRelay, OutboxWorker
from infrastructure.observability.health import InfrastructureReadiness
from presentation.http.app import HttpAppFactory


class PaymentApi(Entrypoint):
    service = "payment-api"
    app: FastAPI

    def __init__(
        self,
        runtime: Runtime,
        relay: OutboxWorker | None = None,
    ) -> None:
        self._runtime = runtime
        self._relay = relay or OutboxRelay(
            runtime.use_cases.publish_outbox,
            interval=runtime.settings.outbox_poll_interval_seconds,
            batch_size=runtime.settings.outbox_batch_size,
        )
        probe = InfrastructureReadiness(
            runtime.resources.engine,
            runtime.resources.broker,
        )
        self.app = HttpAppFactory().create(
            create_payment=runtime.use_cases.create_payment,
            get_payment=runtime.use_cases.get_payment,
            api_key=runtime.settings.api_key,
            lifespan=self.lifespan,
            metrics_text=runtime.render_metrics,
            readiness=probe,
        )

    @classmethod
    def from_env(cls) -> Self:
        return cls(cls.runtime_from_env())

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        await self.start()
        try:
            app.state.runtime = self._runtime
            yield
        finally:
            await self.close()

    async def start(self) -> None:
        await self._runtime.start()
        self._relay.start()

    async def close(self) -> None:
        try:
            await self._relay.stop()
        finally:
            await self._runtime.close()


app = PaymentApi.from_env().app
