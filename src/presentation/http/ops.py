from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

from application.ports import ReadinessCheck


class OpsRouter:
    def __init__(
        self,
        *,
        metrics_text: Callable[[], str] | None = None,
        readiness: ReadinessCheck | None = None,
    ) -> None:
        self._metrics_text = metrics_text
        self._readiness = readiness

    def register(self, app: FastAPI) -> None:
        metrics_text = self._metrics_text
        readiness = self._readiness

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/ready")
        async def ready() -> JSONResponse:
            if readiness is None:
                return JSONResponse({"status": "ok"})
            if await readiness.ready():
                return JSONResponse({"status": "ok"})
            return JSONResponse({"status": "not_ready"}, status_code=503)

        @app.get("/metrics")
        async def prometheus_metrics() -> PlainTextResponse:
            body = metrics_text() if metrics_text is not None else ""
            return PlainTextResponse(body, media_type="text/plain; version=0.0.4")
