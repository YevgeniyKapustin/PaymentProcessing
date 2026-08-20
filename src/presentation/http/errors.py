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
ErrorHandler = Callable[[Request, Exception], Awaitable[JSONResponse]]


class HttpErrorBoundary:
    _RESPONSES: tuple[tuple[type[BaseException], int, str | None], ...] = (
        (IdempotencyConflict, 409, "Idempotency key conflict"),
        (DuplicateIdempotencyKey, 409, "Idempotency key conflict"),
        (PaymentNotFound, 404, "Payment not found"),
        (DomainError, 422, None),
    )

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

    def register(self, app: FastAPI) -> None:
        for exc_type, status, detail in self._RESPONSES:
            app.add_exception_handler(exc_type, self._handler(status, detail))

    @staticmethod
    def _handler(status: int, detail: str | None) -> ErrorHandler:
        async def handle(_request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(
                status_code=status,
                content={"detail": detail if detail is not None else str(exc)},
            )

        return handle
