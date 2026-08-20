from __future__ import annotations

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.ports import Clock
from application.records import GatewayResult
from infrastructure.persistence.models.gateway_charge import GatewayChargeModel


class SqlGatewayResultCache:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def get(self, payment_id: UUID) -> GatewayResult | None:
        async with self._session_factory() as session:
            row = await session.get(GatewayChargeModel, payment_id)
            if row is None:
                return None
            return GatewayResult(is_successful=row.is_successful)

    async def put_if_absent(
        self,
        payment_id: UUID,
        result: GatewayResult,
    ) -> GatewayResult:
        stmt = (
            insert(GatewayChargeModel)
            .values(
                payment_id=payment_id,
                succeeded=result.is_successful,
                created_at=self._clock.now(),
            )
            .on_conflict_do_nothing(index_elements=["payment_id"])
            .returning(GatewayChargeModel.is_successful)
        )
        async with self._session_factory() as session:
            async with session.begin():
                inserted = (await session.execute(stmt)).scalar_one_or_none()
                if inserted is not None:
                    return GatewayResult(is_successful=inserted)
                existing = await session.get(GatewayChargeModel, payment_id)
                if existing is None:
                    raise RuntimeError(f"gateway charge {payment_id} missing")
                return GatewayResult(is_successful=existing.is_successful)
