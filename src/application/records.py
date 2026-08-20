from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class OutboxStatus(StrEnum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboxRecord:
    id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    status: OutboxStatus = OutboxStatus.NEW
    retry_count: int = 0
    published_at: datetime | None = None
    claimed_at: datetime | None = None
    available_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class GatewayResult:
    is_successful: bool
