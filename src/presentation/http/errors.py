from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from application.exceptions import (
    DuplicateIdempotencyKey,
    IdempotencyConflict,
    PaymentNotFound,
)
from domain.exceptions import DomainError
from presentation.http.access import REQUEST_ID_HEADER

log = logging.getLogger(__name__)

CallNext = Callable[[Request], Awaitable[Response]]


class UnhandledErrorMiddleware:
    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        try:
            return await call_next(request)
        except Exception:
            log.exception("http.unhandled_error")
            response = JSONResponse(
                {"detail": "Internal Server Error"},
                status_code=500,
            )
            request_id = getattr(request.state, "request_id", None)
            if request_id:
                response.headers[REQUEST_ID_HEADER] = request_id
            return response


class HttpExceptionHandlers:
    async def conflict(self, request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "Idempotency key conflict"},
        )

    async def not_found(self, request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Payment not found"})

    async def domain_error(self, request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def register(self, app: FastAPI) -> None:
        app.add_exception_handler(IdempotencyConflict, self.conflict)
        app.add_exception_handler(DuplicateIdempotencyKey, self.conflict)
        app.add_exception_handler(PaymentNotFound, self.not_found)
        app.add_exception_handler(DomainError, self.domain_error)
