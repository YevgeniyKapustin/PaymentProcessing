from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from application.ports import ReadinessCheck
from application.use_cases.create_payment import CreatePayment
from application.use_cases.get_payment import GetPayment
from presentation.http.access import AccessLogMiddleware
from presentation.http.errors import HttpErrorBoundary
from presentation.http.ops import OpsRouter
from presentation.http.v1.payments import router as payments_router


class HttpAppFactory:
    def __init__(
        self,
        *,
        errors: HttpErrorBoundary | None = None,
        access_log: AccessLogMiddleware | None = None,
    ) -> None:
        self._errors = errors or HttpErrorBoundary()
        self._access_log = access_log or AccessLogMiddleware()

    def create(
        self,
        *,
        create_payment: CreatePayment,
        get_payment: GetPayment,
        api_key: str,
        lifespan: Any = None,
        metrics_text: Callable[[], str] | None = None,
        readiness: ReadinessCheck | None = None,
    ) -> FastAPI:
        app = FastAPI(title="Payment Service", lifespan=lifespan)
        app.state.create_payment = create_payment
        app.state.get_payment = get_payment
        app.state.api_key = api_key
        app.include_router(payments_router)
        app.middleware("http")(self._errors)
        app.middleware("http")(self._access_log)
        self._errors.register(app)
        OpsRouter(metrics_text=metrics_text, readiness=readiness).register(app)
        return app
