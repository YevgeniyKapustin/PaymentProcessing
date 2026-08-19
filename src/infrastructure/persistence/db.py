from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class PostgresDatabase:
    def __init__(self, url: str) -> None:
        self._url = url

    def create_engine(self) -> AsyncEngine:
        return create_async_engine(
            self._url,
            isolation_level="READ COMMITTED",
            pool_pre_ping=True,
        )

    def create_session_factory(
        self,
        engine: AsyncEngine,
    ) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
