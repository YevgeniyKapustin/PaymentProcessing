from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from structlog.contextvars import bound_contextvars


class LogContext:
    @contextmanager
    def __call__(self, **values: Any) -> Iterator[None]:
        bound = {key: value for key, value in values.items() if value is not None}
        with bound_contextvars(**bound):
            yield


class RequestId:
    def resolve(self, raw: str | None) -> str:
        if raw is None:
            return str(uuid.uuid4())
        candidate = raw.strip()
        if 1 <= len(candidate) <= 128 and candidate.isascii() and candidate.isprintable():
            return candidate
        return str(uuid.uuid4())


log_context = LogContext()
