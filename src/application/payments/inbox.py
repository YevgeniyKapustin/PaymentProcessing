from __future__ import annotations

from uuid import UUID

from application.ports import Clock
from application.uow import UowFactory


class ProcessedMessageInbox:
    def __init__(self, uow_factory: UowFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def seen(self, message_id: UUID) -> bool:
        async with self._uow_factory() as uow:
            return await uow.inbox.exists(message_id)

    async def remember(self, message_id: UUID) -> None:
        async with self._uow_factory() as uow:
            await uow.inbox.add(message_id, self._clock.now())
            await uow.commit()
