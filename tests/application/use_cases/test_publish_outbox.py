import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from application.outbox.codec import EVENT_VERSION, OUTBOX_ID_HEADER, OutboxEventCodec
from application.outbox.routing import NEW_ROUTING_KEY
from application.payments.events import PAYMENT_CREATED
from application.records import OutboxRecord, OutboxStatus
from application.use_cases.publish_outbox import PublishOutbox
from infrastructure.observability.metrics import PrometheusOutboxMetrics
from tests.application.fakes import (
    FakePublisher,
    FrozenClock,
    InMemoryStore,
    make_uow_factory,
)

CLOCK = FrozenClock(datetime(2026, 8, 18, tzinfo=UTC))


def _record(payload: dict, **overrides: object) -> OutboxRecord:
    data = {
        "id": uuid4(),
        "event_type": PAYMENT_CREATED,
        "payload": payload,
        "created_at": CLOCK.now(),
        "status": OutboxStatus.NEW,
        "retry_count": 0,
        "published_at": None,
        "claimed_at": None,
        "available_at": None,
    }
    data.update(overrides)
    return OutboxRecord(**data)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_empty_outbox_publishes_nothing() -> None:
    store = InMemoryStore()
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    assert await use_case.execute() == 0
    assert publisher.messages == []


@pytest.mark.asyncio
async def test_publishes_envelope_then_marks_processed() -> None:
    store = InMemoryStore()
    first = _record({"payment_id": "a"})
    second = _record({"payment_id": "b"})
    store.outbox.extend([first, second])
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK, batch_size=10)
    assert await use_case.execute() == 2
    routing, body, headers, _exp = publisher.messages[0]
    assert routing == NEW_ROUTING_KEY
    decoded = json.loads(body)
    assert decoded["event_type"] == PAYMENT_CREATED
    assert decoded["event_version"] == EVENT_VERSION
    assert decoded["payload"] == {"payment_id": "a"}
    assert decoded["outbox_id"] == str(first.id)
    assert headers is not None
    assert headers[OUTBOX_ID_HEADER] == str(first.id)
    published = {row.id: row for row in store.outbox}
    assert published[first.id].status is OutboxStatus.PROCESSED
    assert published[first.id].published_at == CLOCK.now()
    assert published[second.id].status is OutboxStatus.PROCESSED


@pytest.mark.asyncio
async def test_batch_size_limits_publish() -> None:
    store = InMemoryStore()
    rows = [_record({"payment_id": name}) for name in ("a", "b", "c")]
    store.outbox.extend(rows)
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK, batch_size=2)
    assert await use_case.execute() == 2
    assert len(publisher.messages) == 2
    published = {row.id: row for row in store.outbox}
    assert published[rows[0].id].status is OutboxStatus.PROCESSED
    assert published[rows[1].id].status is OutboxStatus.PROCESSED
    assert published[rows[2].id].status is OutboxStatus.NEW


@pytest.mark.asyncio
async def test_publish_failure_unclaims_without_retry_count() -> None:
    store = InMemoryStore()
    row = _record({"payment_id": "a"})
    store.outbox.append(row)
    publisher = FakePublisher(error=RuntimeError("broker down"))
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    with pytest.raises(RuntimeError, match="broker down"):
        await use_case.execute()
    stored = store.outbox[0]
    assert stored.status is OutboxStatus.NEW
    assert stored.retry_count == 0
    assert stored.published_at is None


@pytest.mark.asyncio
async def test_poison_row_does_not_block_later_rows() -> None:
    store = InMemoryStore()
    first = _record({"payment_id": "a"})
    second = _record({"payment_id": "b"})
    store.outbox.extend([first, second])
    publisher = FakePublisher(error=RuntimeError("bad payload"), fail_on=2)
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        max_attempts=3,
    )
    assert await use_case.execute() == 1
    by_id = {row.id: row for row in store.outbox}
    assert by_id[first.id].status is OutboxStatus.PROCESSED
    assert by_id[second.id].status is OutboxStatus.NEW
    assert by_id[second.id].retry_count == 1


@pytest.mark.asyncio
async def test_poison_row_fails_after_max_attempts() -> None:
    store = InMemoryStore()
    good = _record({"payment_id": "ok"})
    poison = _record({"payment_id": "bad"}, retry_count=7)
    store.outbox.extend([good, poison])
    publisher = FakePublisher(error=RuntimeError("bad payload"), fail_on=2)
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        max_attempts=8,
    )
    assert await use_case.execute() == 1
    by_id = {row.id: row for row in store.outbox}
    assert by_id[poison.id].status is OutboxStatus.FAILED
    assert by_id[poison.id].retry_count == 8
    assert by_id[poison.id].available_at is None


@pytest.mark.asyncio
async def test_retry_schedules_available_at() -> None:
    store = InMemoryStore()
    first = _record({"payment_id": "a"})
    second = _record({"payment_id": "b"})
    store.outbox.extend([first, second])
    publisher = FakePublisher(error=RuntimeError("bad payload"), fail_on=2)
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        max_attempts=8,
        retry_initial_seconds=1.0,
        retry_cap_seconds=60.0,
        use_jitter=False,
    )
    assert await use_case.execute() == 1
    delayed = {row.id: row for row in store.outbox}[second.id]
    assert delayed.status is OutboxStatus.NEW
    assert delayed.retry_count == 1
    assert delayed.available_at == CLOCK.now() + timedelta(seconds=1)


@pytest.mark.asyncio
async def test_skips_row_until_available_at() -> None:
    store = InMemoryStore()
    store.outbox.append(
        _record(
            {"payment_id": "later"},
            available_at=CLOCK.now() + timedelta(seconds=5),
        )
    )
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    assert await use_case.execute() == 0
    assert publisher.messages == []
    assert store.outbox[0].status is OutboxStatus.NEW


@pytest.mark.asyncio
async def test_claims_row_when_available_at_is_due() -> None:
    store = InMemoryStore()
    store.outbox.append(_record({"payment_id": "due"}, available_at=CLOCK.now(), retry_count=1))
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    assert await use_case.execute() == 1
    assert store.outbox[0].status is OutboxStatus.PROCESSED


@pytest.mark.asyncio
async def test_failed_count_is_exported() -> None:
    store = InMemoryStore()
    good = _record({"payment_id": "ok"})
    poison = _record({"payment_id": "bad"}, retry_count=7)
    store.outbox.extend([good, poison])
    metrics = PrometheusOutboxMetrics()
    use_case = PublishOutbox(
        make_uow_factory(store),
        FakePublisher(error=RuntimeError("bad payload"), fail_on=2),
        CLOCK,
        max_attempts=8,
        metrics=metrics,
    )
    assert await use_case.execute() == 1
    assert "outbox_failed 1" in metrics.render()


@pytest.mark.asyncio
async def test_permanently_failed_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryStore()
    good = _record({"payment_id": "ok"})
    poison = _record({"payment_id": "bad"}, retry_count=7)
    store.outbox.extend([good, poison])
    use_case = PublishOutbox(
        make_uow_factory(store),
        FakePublisher(error=RuntimeError("bad payload"), fail_on=2),
        CLOCK,
        max_attempts=8,
    )
    with caplog.at_level("WARNING"):
        await use_case.execute()
    failed_logs = [
        record for record in caplog.records if record.getMessage() == "outbox.permanently_failed"
    ]
    assert failed_logs
    assert getattr(failed_logs[0], "outbox_id") == str(poison.id)
    assert getattr(failed_logs[0], "payment_id") == "bad"


@pytest.mark.asyncio
async def test_purges_old_processed_rows_when_idle() -> None:
    store = InMemoryStore()
    old = _record(
        {"payment_id": "old"},
        status=OutboxStatus.PROCESSED,
        published_at=CLOCK.now() - timedelta(days=4),
    )
    store.outbox.append(old)
    use_case = PublishOutbox(
        make_uow_factory(store),
        FakePublisher(),
        CLOCK,
        retention_days=3,
    )
    assert await use_case.execute() == 0
    assert store.outbox == []


@pytest.mark.asyncio
async def test_unclaim_with_no_ids_is_noop() -> None:
    store = InMemoryStore()
    use_case = PublishOutbox(make_uow_factory(store), FakePublisher(), CLOCK)
    await use_case._unclaim([])
    assert store.outbox == []


def test_encode_outbox_event_wraps_payload() -> None:
    record = _record({"payment_id": "x"})
    body, headers = OutboxEventCodec().encode(record)
    decoded = json.loads(body)
    assert decoded["payload"]["payment_id"] == "x"
    assert headers[OUTBOX_ID_HEADER] == str(record.id)
