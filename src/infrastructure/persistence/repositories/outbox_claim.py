from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from application.records import OutboxStatus
from infrastructure.persistence.models.outbox import OutboxModel


class OutboxClaimFilter:
    def build(
        self,
        now: datetime,
        stale_before: datetime,
    ) -> ColumnElement[bool]:
        due = or_(
            OutboxModel.available_at.is_(None),
            OutboxModel.available_at <= now,
        )
        new_due = and_(OutboxModel.status == OutboxStatus.NEW, due)
        stale = and_(
            OutboxModel.status == OutboxStatus.PROCESSING,
            OutboxModel.claimed_at.is_not(None),
            OutboxModel.claimed_at <= stale_before,
        )
        return or_(new_due, stale)
