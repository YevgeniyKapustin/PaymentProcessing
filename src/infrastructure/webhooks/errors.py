from __future__ import annotations

from application.exceptions import (
    PermanentProcessingError,
    TransientDependencyError,
)


class WebhookErrorMapper:
    def timeout(self) -> TransientDependencyError:
        return TransientDependencyError("webhook timeout")

    def transport(self) -> TransientDependencyError:
        return TransientDependencyError("webhook transport error")

    def from_status(self, status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        if 400 <= status_code < 500:
            raise PermanentProcessingError(
                f"webhook rejected with {status_code}",
            )
        raise TransientDependencyError(f"webhook failed with {status_code}")
