from __future__ import annotations

from datetime import datetime

from application.records import OutboxRecord, OutboxStatus
from infrastructure.persistence.models.outbox import OutboxModel


class OutboxMapper:
    def to_claimed_record(
        self,
        row: OutboxModel,
        claimed_at: datetime,
    ) -> OutboxRecord:
        return OutboxRecord(
            id=row.id,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
            status=OutboxStatus.PROCESSING,
            retry_count=row.retry_count,
            published_at=row.published_at,
            claimed_at=claimed_at,
            available_at=None,
        )
