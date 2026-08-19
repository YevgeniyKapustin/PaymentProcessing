from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from application.exceptions import (
    DuplicateIdempotencyKey,
    IdempotencyConflict,
    PaymentNotFound,
)
from domain.exceptions import DomainError


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
