from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.observability.health import InfrastructureReadiness


class _Conn:
    async def execute(self, _stmt: object) -> None:
        return None

    async def __aenter__(self) -> _Conn:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


def _engine() -> MagicMock:
    engine = MagicMock()
    engine.connect.return_value = _Conn()
    return engine


@pytest.mark.asyncio
async def test_ready_when_postgres_and_rabbit_respond() -> None:
    broker = SimpleNamespace(ping=AsyncMock(return_value=True))
    probe = InfrastructureReadiness(_engine(), broker)
    assert await probe.is_ready() is True
    broker.ping.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_not_ready_when_rabbit_is_down() -> None:
    broker = SimpleNamespace(ping=AsyncMock(return_value=False))
    probe = InfrastructureReadiness(_engine(), broker)
    assert await probe.is_ready() is False


@pytest.mark.asyncio
async def test_not_ready_when_postgres_raises() -> None:
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("db down")
    broker = SimpleNamespace(ping=AsyncMock(return_value=True))
    probe = InfrastructureReadiness(engine, broker)
    assert await probe.is_ready() is False
