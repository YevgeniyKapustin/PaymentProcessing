from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from application.records import OutboxStatus
from infrastructure.persistence.models.outbox import OutboxModel


class SqlOutboxWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
