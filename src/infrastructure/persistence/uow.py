from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.ports import (
    InboxRepository,
    OutboxQueue,
    OutboxWriter,
    PaymentRepository,
)
from infrastructure.persistence.repositories.inbox import SqlInboxRepository
from infrastructure.persistence.repositories.outbox_queue import SqlOutboxQueue
from infrastructure.persistence.repositories.outbox_writer import SqlOutboxWriter
from infrastructure.persistence.repositories.payment import SqlPaymentRepository


class SqlAlchemyUnitOfWork:
    payments: PaymentRepository
    outbox: OutboxWriter
    outbox_queue: OutboxQueue
    inbox: InboxRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return self._session

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.payments = SqlPaymentRepository(self._session)
        self.outbox = SqlOutboxWriter(self._session)
        self.outbox_queue = SqlOutboxQueue(self._session)
        self.inbox = SqlInboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        session = self._require_session()
        if exc_type is not None:
            await self.rollback()
        await session.close()
        self._session = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()
