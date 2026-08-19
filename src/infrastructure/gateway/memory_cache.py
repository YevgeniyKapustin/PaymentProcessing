from __future__ import annotations

from uuid import UUID

from application.records import GatewayResult


class InMemoryGatewayResultCache:
    def __init__(self) -> None:
        self._results: dict[UUID, GatewayResult] = {}

    async def get(self, payment_id: UUID) -> GatewayResult | None:
        return self._results.get(payment_id)

    async def put_if_absent(
        self,
        payment_id: UUID,
        result: GatewayResult,
    ) -> GatewayResult:
        existing = self._results.get(payment_id)
        if existing is not None:
            return existing
        self._results[payment_id] = result
        return result
