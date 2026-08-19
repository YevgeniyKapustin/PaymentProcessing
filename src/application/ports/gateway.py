from __future__ import annotations

from typing import Protocol
from uuid import UUID

from application.records import GatewayResult
from domain.payment import Payment


class GatewayResultCache(Protocol):
    async def get(self, payment_id: UUID) -> GatewayResult | None: ...

    async def put_if_absent(
        self,
        payment_id: UUID,
        result: GatewayResult,
    ) -> GatewayResult: ...


class PaymentGateway(Protocol):
    async def charge(self, payment: Payment) -> GatewayResult: ...
