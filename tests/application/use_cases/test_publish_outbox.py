import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from application.outbox.codec import (
    EVENT_TYPE_HEADER,
    EVENT_VERSION,
    OUTBOX_ID_HEADER,
    OutboxEventCodec,
)
from application.outbox.routing import NEW_ROUTING_KEY
from application.payments.events import PAYMENT_CREATED
from application.records import OutboxRecord, OutboxStatus
from application.use_cases.publish_outbox import PublishOutbox
from infrastructure.observability.metrics import PrometheusOutboxMetrics
from tests.application.fakes import (
    FakePublisher,
    FrozenClock,
    InMemoryStore,
    InMemoryUnitOfWork,
    make_uow_factory,
)

CLOCK = FrozenClock(datetime(2026, 8, 18, tzinfo=UTC))


class MovingClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def advance(self, delta: timedelta) -> None:
        self._moment = self._moment + delta


class _AckSpyPublisher:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self.status_at_publish: OutboxStatus | None = None
        self.messages: list[tuple[str, bytes, dict[str, Any] | None, int | None]] = []

    async def publish(
        self,
        routing_key: str,
        body: bytes,
        *,
        headers: Mapping[str, Any] | None = None,
        expiration: int | None = None,
    ) -> None:
        self.status_at_publish = self._store.outbox[0].status
        stored = dict(headers) if headers is not None else None
        self.messages.append((routing_key, body, stored, expiration))


def make_mark_processed_failing_factory(
    store: InMemoryStore,
    fail_times: int = 1,
):
    remaining = fail_times

    def factory() -> InMemoryUnitOfWork:
        nonlocal remaining
        uow = InMemoryUnitOfWork(store)
        original = uow.outbox.mark_processed

        async def mark_processed(record_id: object, published_at: object) -> None:
            nonlocal remaining
            if remaining > 0:
                remaining -= 1
                raise RuntimeError("crashed after publish")
            await original(record_id, published_at)  # type: ignore[arg-type]

        uow.outbox.mark_processed = mark_processed  # type: ignore[method-assign]
        return uow

    return factory


class _CountingGauges:
    def __init__(self) -> None:
        self.calls = 0

    async def refresh(self) -> None:
        self.calls += 1


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
    assert headers[EVENT_TYPE_HEADER] == PAYMENT_CREATED
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
async def test_publish_failure_retries_with_backoff() -> None:
    store = InMemoryStore()
    row = _record({"payment_id": "a"})
    store.outbox.append(row)
    publisher = FakePublisher(error=RuntimeError("broker down"))
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        retry_initial_seconds=1.0,
        use_jitter=False,
    )
    assert await use_case.execute() == 0
    stored = store.outbox[0]
    assert stored.status is OutboxStatus.NEW
    assert stored.retry_count == 1
    assert stored.published_at is None
    assert stored.available_at == CLOCK.now() + timedelta(seconds=1)
    assert stored.claimed_at is None


@pytest.mark.asyncio
async def test_first_row_failure_does_not_block_later_rows() -> None:
    store = InMemoryStore()
    first = _record({"payment_id": "a"})
    second = _record({"payment_id": "b"})
    third = _record({"payment_id": "c"})
    store.outbox.extend([first, second, third])
    publisher = FakePublisher(error=RuntimeError("bad payload"), fail_on=1)
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        max_attempts=3,
        retry_initial_seconds=1.0,
        use_jitter=False,
    )
    assert await use_case.execute() == 2
    by_id = {row.id: row for row in store.outbox}
    assert by_id[first.id].status is OutboxStatus.NEW
    assert by_id[first.id].retry_count == 1
    assert by_id[first.id].claimed_at is None
    assert by_id[second.id].status is OutboxStatus.PROCESSED
    assert by_id[third.id].status is OutboxStatus.PROCESSED


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
async def test_gauges_refresh_once_when_idle() -> None:
    store = InMemoryStore()
    gauges = AsyncMock()
    use_case = PublishOutbox(
        make_uow_factory(store),
        FakePublisher(),
        CLOCK,
        gauges=gauges,
    )
    assert await use_case.execute() == 0
    assert gauges.refresh.await_count == 1


@pytest.mark.asyncio
async def test_gauges_refresh_once_after_batch() -> None:
    store = InMemoryStore()
    store.outbox.append(_record({"payment_id": "a"}))
    gauges = AsyncMock()
    use_case = PublishOutbox(
        make_uow_factory(store),
        FakePublisher(),
        CLOCK,
        gauges=gauges,
    )
    assert await use_case.execute() == 1
    assert gauges.refresh.await_count == 1


def test_encode_outbox_event_wraps_payload() -> None:
    record = _record({"payment_id": "x"})
    body, headers = OutboxEventCodec().encode(record)
    decoded = json.loads(body)
    assert decoded["payload"]["payment_id"] == "x"
    assert headers[OUTBOX_ID_HEADER] == str(record.id)


@pytest.mark.asyncio
async def test_does_not_mark_processed_until_broker_acks() -> None:
    store = InMemoryStore()
    store.outbox.append(_record({"payment_id": "a"}))
    publisher = _AckSpyPublisher(store)
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    assert await use_case.execute() == 1
    assert publisher.status_at_publish is OutboxStatus.PROCESSING
    assert store.outbox[0].status is OutboxStatus.PROCESSED
    assert store.outbox[0].published_at == CLOCK.now()


@pytest.mark.asyncio
async def test_timeout_is_retried_without_losing_row() -> None:
    store = InMemoryStore()
    store.outbox.append(_record({"payment_id": "a"}))
    publisher = FakePublisher(error=TimeoutError("broker timeout"))
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        retry_initial_seconds=1.0,
        use_jitter=False,
    )
    assert await use_case.execute() == 0
    stored = store.outbox[0]
    assert stored.status is OutboxStatus.NEW
    assert stored.retry_count == 1
    assert stored.published_at is None
    assert stored.available_at == CLOCK.now() + timedelta(seconds=1)
    assert publisher.messages == []


@pytest.mark.asyncio
async def test_broker_recovery_publishes_pending_rows() -> None:
    clock = MovingClock(CLOCK.now())
    store = InMemoryStore()
    store.outbox.append(_record({"payment_id": "a"}))
    publisher = FakePublisher(error=RuntimeError("broker down"))
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        clock,
        retry_initial_seconds=1.0,
        use_jitter=False,
    )
    assert await use_case.execute() == 0
    publisher.error = None
    clock.advance(timedelta(seconds=1))
    assert await use_case.execute() == 1
    assert store.outbox[0].status is OutboxStatus.PROCESSED
    assert len(publisher.messages) == 1


@pytest.mark.asyncio
async def test_retry_backoff_doubles_on_consecutive_failures() -> None:
    clock = MovingClock(CLOCK.now())
    store = InMemoryStore()
    store.outbox.append(_record({"payment_id": "a"}))
    publisher = FakePublisher(error=RuntimeError("broker down"))
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        clock,
        retry_initial_seconds=1.0,
        use_jitter=False,
    )
    await use_case.execute()
    assert store.outbox[0].available_at == clock.now() + timedelta(seconds=1)
    clock.advance(timedelta(seconds=1))
    await use_case.execute()
    assert store.outbox[0].retry_count == 2
    assert store.outbox[0].status is OutboxStatus.NEW
    assert store.outbox[0].available_at == clock.now() + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_stale_processing_row_is_republished() -> None:
    store = InMemoryStore()
    row = _record(
        {"payment_id": "a"},
        status=OutboxStatus.PROCESSING,
        claimed_at=CLOCK.now() - timedelta(seconds=61),
    )
    store.outbox.append(row)
    publisher = FakePublisher()
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        claim_timeout_seconds=60.0,
    )
    assert await use_case.execute() == 1
    assert store.outbox[0].status is OutboxStatus.PROCESSED
    headers = publisher.messages[0][2]
    assert headers is not None
    assert headers[OUTBOX_ID_HEADER] == str(row.id)


@pytest.mark.asyncio
async def test_in_flight_processing_row_is_not_claimed() -> None:
    store = InMemoryStore()
    store.outbox.append(
        _record(
            {"payment_id": "a"},
            status=OutboxStatus.PROCESSING,
            claimed_at=CLOCK.now(),
        )
    )
    publisher = FakePublisher()
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        claim_timeout_seconds=60.0,
    )
    assert await use_case.execute() == 0
    assert publisher.messages == []
    assert store.outbox[0].status is OutboxStatus.PROCESSING


@pytest.mark.asyncio
async def test_crash_after_publish_still_republishes() -> None:
    store = InMemoryStore()
    row = _record({"payment_id": "a"})
    store.outbox.append(row)
    publisher = FakePublisher()
    clock = MovingClock(CLOCK.now())
    use_case = PublishOutbox(
        make_mark_processed_failing_factory(store),
        publisher,
        clock,
        retry_initial_seconds=1.0,
        use_jitter=False,
    )
    assert await use_case.execute() == 0
    assert len(publisher.messages) == 1
    assert store.outbox[0].status is OutboxStatus.NEW
    assert store.outbox[0].published_at is None
    clock.advance(timedelta(seconds=1))
    assert await use_case.execute() == 1
    assert len(publisher.messages) == 2
    first_headers = publisher.messages[0][2]
    second_headers = publisher.messages[1][2]
    assert first_headers is not None
    assert second_headers is not None
    assert first_headers[OUTBOX_ID_HEADER] == str(row.id)
    assert second_headers[OUTBOX_ID_HEADER] == str(row.id)
    assert store.outbox[0].status is OutboxStatus.PROCESSED


@pytest.mark.asyncio
async def test_publishes_in_created_at_order() -> None:
    store = InMemoryStore()
    payment_id = str(uuid4())
    later = _record(
        {"payment_id": payment_id, "step": "later"},
        created_at=CLOCK.now() + timedelta(seconds=1),
    )
    earlier = _record(
        {"payment_id": payment_id, "step": "earlier"},
        created_at=CLOCK.now(),
    )
    store.outbox.extend([later, earlier])
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    assert await use_case.execute() == 2
    first = json.loads(publisher.messages[0][1])
    second = json.loads(publisher.messages[1][1])
    assert first["payload"]["step"] == "earlier"
    assert second["payload"]["step"] == "later"


@pytest.mark.asyncio
async def test_failed_row_is_not_claimed() -> None:
    store = InMemoryStore()
    store.outbox.append(
        _record(
            {"payment_id": "dead"},
            status=OutboxStatus.FAILED,
            retry_count=8,
        )
    )
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    assert await use_case.execute() == 0
    assert publisher.messages == []
    assert store.outbox[0].status is OutboxStatus.FAILED


@pytest.mark.asyncio
async def test_processed_row_is_not_republished() -> None:
    store = InMemoryStore()
    store.outbox.append(
        _record(
            {"payment_id": "a"},
            status=OutboxStatus.PROCESSED,
            published_at=CLOCK.now(),
        )
    )
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK)
    assert await use_case.execute() == 0
    assert publisher.messages == []
    assert store.outbox[0].status is OutboxStatus.PROCESSED


@pytest.mark.asyncio
async def test_non_serializable_payload_does_not_block_later_rows() -> None:
    store = InMemoryStore()
    poison = _record({"payment_id": "bad", "blob": object()})
    good = _record({"payment_id": "ok"})
    store.outbox.extend([poison, good])
    publisher = FakePublisher()
    use_case = PublishOutbox(
        make_uow_factory(store),
        publisher,
        CLOCK,
        max_attempts=3,
        retry_initial_seconds=1.0,
        use_jitter=False,
    )
    assert await use_case.execute() == 1
    by_id = {row.id: row for row in store.outbox}
    assert by_id[poison.id].status is OutboxStatus.NEW
    assert by_id[poison.id].retry_count == 1
    assert by_id[good.id].status is OutboxStatus.PROCESSED
    assert len(publisher.messages) == 1


@pytest.mark.asyncio
async def test_remaining_rows_are_published_on_next_execute() -> None:
    store = InMemoryStore()
    rows = [_record({"payment_id": name}) for name in ("a", "b", "c")]
    store.outbox.extend(rows)
    publisher = FakePublisher()
    use_case = PublishOutbox(make_uow_factory(store), publisher, CLOCK, batch_size=2)
    assert await use_case.execute() == 2
    assert await use_case.execute() == 1
    assert len(publisher.messages) == 3
    published = {row.id: row for row in store.outbox}
    assert all(row.status is OutboxStatus.PROCESSED for row in published.values())
