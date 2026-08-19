from __future__ import annotations

import hmac

from fastapi import HTTPException


class ApiKeyAuthenticator:
    def verify(self, provided: str | None, expected: str) -> None:
        if provided is None or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Unauthorized")
