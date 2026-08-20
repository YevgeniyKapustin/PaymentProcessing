from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.persistence.models.inbox import InboxModel


class SqlInboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_message(self, message_id: UUID) -> bool:
        model = await self._session.get(InboxModel, message_id)
        return model is not None

    async def add(self, message_id: UUID, processed_at: datetime) -> None:
        try:
            async with self._session.begin_nested():
                self._session.add(
                    InboxModel(message_id=message_id, processed_at=processed_at),
                )
                await self._session.flush()
        except IntegrityError:
            return
