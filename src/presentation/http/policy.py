from __future__ import annotations

import logging


class AccessLogPolicy:
    SKIP_SUCCESS_PATHS = frozenset(
        {"/health", "/ready", "/docs", "/redoc", "/openapi.json"},
    )

    def choose_log_level(self, status_code: int) -> int:
        if status_code >= 500:
            return logging.ERROR
        if status_code >= 400:
            return logging.WARNING
        return logging.INFO

    def should_log(self, path: str, status_code: int) -> bool:
        if path in self.SKIP_SUCCESS_PATHS and status_code < 400:
            return False
        return True
