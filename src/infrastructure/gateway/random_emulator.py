from __future__ import annotations

from application.ports import GatewayResultCache
from application.records import GatewayResult
from domain.payment import Payment
from infrastructure.gateway.delay import UniformRandomDelay
from infrastructure.gateway.memory_cache import InMemoryGatewayResultCache
from infrastructure.gateway.outcome import RandomChargeOutcome


class RandomPaymentGateway:
    def __init__(
        self,
        *,
        min_delay_seconds: float = 2.0,
        max_delay_seconds: float = 5.0,
        success_rate: float = 0.9,
        delay: UniformRandomDelay | None = None,
        outcome: RandomChargeOutcome | None = None,
        cache: GatewayResultCache | None = None,
    ) -> None:
        self._delay = delay or UniformRandomDelay(
            min_delay_seconds,
            max_delay_seconds,
        )
        self._outcome = outcome or RandomChargeOutcome(success_rate)
        self._cache = cache or InMemoryGatewayResultCache()

    async def charge(self, payment: Payment) -> GatewayResult:
        payment_id = payment.id.value
        cached = await self._cache.get(payment_id)
        if cached is not None:
            return cached
        await self._delay.wait()
        result = GatewayResult(is_successful=self._outcome.is_successful())
        return await self._cache.put_if_absent(payment_id, result)
