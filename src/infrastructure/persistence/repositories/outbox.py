from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from application.records import OutboxRecord, OutboxStatus
from infrastructure.persistence.mappers.outbox import OutboxMapper
from infrastructure.persistence.models.outbox import OutboxModel
from infrastructure.persistence.repositories.outbox_claim import OutboxClaimFilter


class SqlOutboxRepository:
    def __init__(
        self,
        session: AsyncSession,
        mapper: OutboxMapper | None = None,
        claim_filter: OutboxClaimFilter | None = None,
    ) -> None:
        self._session = session
        self._mapper = mapper or OutboxMapper()
        self._claim_filter = claim_filter or OutboxClaimFilter()

    async def add(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self._session.add(
            OutboxModel(
                id=uuid4(),
                event_type=event_type,
                payload=payload,
                created_at=created_at,
                published_at=None,
                status=OutboxStatus.NEW,
                retry_count=0,
                claimed_at=None,
                available_at=None,
            )
        )

    async def claim_batch(
        self,
        limit: int,
        *,
        now: datetime,
        stale_before: datetime,
    ) -> list[OutboxRecord]:
        stmt = (
            select(OutboxModel)
            .where(self._claim_filter.expression(now, stale_before))
            .order_by(OutboxModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars())
        if not rows:
            return []
        ids = [row.id for row in rows]
        await self._session.execute(
            update(OutboxModel)
            .where(OutboxModel.id.in_(ids))
            .values(
                status=OutboxStatus.PROCESSING,
                claimed_at=now,
                available_at=None,
            )
        )
        return [self._mapper.to_claimed_record(row, now) for row in rows]

    async def mark_processed(
        self,
        record_id: UUID,
        published_at: datetime,
    ) -> None:
        stmt = (
            update(OutboxModel)
            .where(OutboxModel.id == record_id)
            .values(
                status=OutboxStatus.PROCESSED,
                published_at=published_at,
                claimed_at=None,
                available_at=None,
            )
        )
        await self._session.execute(stmt)

    async def release(
        self,
        record_id: UUID,
        *,
        status: OutboxStatus,
        retry_count: int,
        available_at: datetime | None = None,
    ) -> None:
        stmt = (
            update(OutboxModel)
            .where(OutboxModel.id == record_id)
            .values(
                status=status,
                retry_count=retry_count,
                claimed_at=None,
                available_at=available_at,
            )
        )
        await self._session.execute(stmt)

    async def unclaim(self, ids: Sequence[UUID]) -> None:
        if not ids:
            return
        stmt = (
            update(OutboxModel)
            .where(OutboxModel.id.in_(ids))
            .values(status=OutboxStatus.NEW, claimed_at=None, available_at=None)
        )
        await self._session.execute(stmt)

    async def count_pending(self) -> int:
        stmt = select(func.count()).where(
            OutboxModel.status.in_((OutboxStatus.NEW, OutboxStatus.PROCESSING))
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_failed(self) -> int:
        stmt = select(func.count()).where(OutboxModel.status == OutboxStatus.FAILED)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def delete_processed_before(
        self,
        cutoff: datetime,
        limit: int,
    ) -> int:
        ids = (
            select(OutboxModel.id)
            .where(
                OutboxModel.status == OutboxStatus.PROCESSED,
                OutboxModel.published_at.is_not(None),
                OutboxModel.published_at < cutoff,
            )
            .limit(limit)
        )
        result = await self._session.execute(
            delete(OutboxModel).where(OutboxModel.id.in_(ids)),
        )
        return int(getattr(result, "rowcount", 0) or 0)
