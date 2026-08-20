from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from presentation.http.policy import AccessLogPolicy
from presentation.log_context import RequestId, log_context

log = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
CallNext = Callable[[Request], Awaitable[Response]]


class RequestTimer:
    def __init__(self) -> None:
        self._started = time.perf_counter()

    def duration_ms(self) -> float:
        return round((time.perf_counter() - self._started) * 1000, 2)


class AccessLogMiddleware:
    def __init__(
        self,
        *,
        policy: AccessLogPolicy | None = None,
        request_ids: RequestId | None = None,
    ) -> None:
        self._policy = policy or AccessLogPolicy()
        self._request_ids = request_ids or RequestId()

    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        request_id = self._request_ids.resolve(
            request.headers.get(REQUEST_ID_HEADER),
        )
        request.state.request_id = request_id
        timer = RequestTimer()
        with log_context(request_id=request_id):
            response = await call_next(request)
            self._log_access(
                request,
                status_code=response.status_code,
                duration_ms=timer.duration_ms(),
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response

    def _log_access(
        self,
        request: Request,
        *,
        status_code: int,
        duration_ms: float,
    ) -> None:
        if not self._policy.should_log(request.url.path, status_code):
            return
        log.log(
            self._policy.level_for(status_code),
            "http.request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
