from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Self

from fastapi import FastAPI

from runtime import Runtime
from presentation.base import Entrypoint
from infrastructure.observability.health import InfrastructureReadiness
from presentation.http.app import HttpAppFactory


class PaymentApi(Entrypoint):
    service = "payment-api"
    app: FastAPI

    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        probe = InfrastructureReadiness(
            runtime.resources.engine,
            runtime.resources.broker,
        )
        self.app = HttpAppFactory().create(
            create_payment=runtime.use_cases.create_payment,
            get_payment=runtime.use_cases.get_payment,
            api_key=runtime.settings.api_key,
            lifespan=self.lifespan,
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

    async def close(self) -> None:
        await self._runtime.close()


def create_app() -> FastAPI:
    return PaymentApi.from_env().app
