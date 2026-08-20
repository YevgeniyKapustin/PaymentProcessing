from datetime import UTC, datetime
from uuid import uuid4

from application.records import OutboxStatus
from infrastructure.persistence.mappers.outbox import OutboxMapper
from infrastructure.persistence.models.outbox import OutboxModel


def test_to_claimed_record_marks_processing() -> None:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    claimed = datetime(2026, 1, 2, tzinfo=UTC)
    row = OutboxModel(
        id=uuid4(),
        event_type="PaymentCreated",
        payload={"payment_id": "x"},
        created_at=created,
        published_at=None,
        status=OutboxStatus.NEW,
        retry_count=1,
        claimed_at=None,
        available_at=created,
    )
    record = OutboxMapper().to_claimed_record(row, claimed)
    assert record.id == row.id
    assert record.event_type == "PaymentCreated"
    assert record.payload == {"payment_id": "x"}
    assert record.created_at == created
    assert record.status is OutboxStatus.PROCESSING
    assert record.retry_count == 1
    assert record.published_at is None
    assert record.claimed_at == claimed
    assert record.available_at is None
