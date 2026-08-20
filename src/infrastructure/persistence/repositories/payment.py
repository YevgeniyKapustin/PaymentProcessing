from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.exceptions import DuplicateIdempotencyKey
from domain.ids import IdempotencyKey, PaymentId
from domain.payment import Payment
from infrastructure.persistence.mappers.payment import PaymentMapper
from infrastructure.persistence.models.payment import PaymentModel
from infrastructure.persistence.repositories.idempotency import IdempotencyConstraint


class SqlPaymentRepository:
    def __init__(
        self,
        session: AsyncSession,
        mapper: PaymentMapper | None = None,
        idempotency: IdempotencyConstraint | None = None,
    ) -> None:
        self._session = session
        self._mapper = mapper or PaymentMapper()
        self._idempotency = idempotency or IdempotencyConstraint()

    async def add(self, payment: Payment) -> None:
        self._session.add(self._mapper.to_model(payment))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if self._idempotency.is_idempotency_conflict(exc):
                raise DuplicateIdempotencyKey from exc
            raise

    async def save(self, payment: Payment) -> None:
        model = await self._session.get(PaymentModel, payment.id.value)
        if model is None:
            raise RuntimeError(f"payment {payment.id.value} missing for save")
        self._mapper.apply(model, payment)
        await self._session.flush()

    async def get(self, payment_id: PaymentId) -> Payment | None:
        model = await self._session.get(PaymentModel, payment_id.value)
        if model is None:
            return None
        return self._mapper.to_domain(model)

    async def get_for_update(self, payment_id: PaymentId) -> Payment | None:
        stmt = select(PaymentModel).where(PaymentModel.id == payment_id.value).with_for_update()
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._mapper.to_domain(model)

    async def get_by_idempotency_key(self, key: IdempotencyKey) -> Payment | None:
        stmt = select(PaymentModel).where(PaymentModel.idempotency_key == key.value)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._mapper.to_domain(model)
