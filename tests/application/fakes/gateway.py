from __future__ import annotations

from uuid import UUID

from application.records import GatewayResult
from domain.payment import Payment


class FakeGateway:
    def __init__(
        self,
        is_successful: bool = True,
        error: BaseException | None = None,
    ) -> None:
        self.is_successful = is_successful
        self.error = error
        self.calls = 0
        self._results: dict[UUID, GatewayResult] = {}

    @property
    def captures(self) -> int:
        return len(self._results)

    async def charge(self, payment: Payment) -> GatewayResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        cached = self._results.get(payment.id.value)
        if cached is not None:
            return cached
        result = GatewayResult(is_successful=self.is_successful)
        self._results[payment.id.value] = result
        return result
