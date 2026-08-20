import json
from datetime import UTC, datetime
from uuid import uuid4

from application.outbox.codec import (
    EVENT_TYPE_HEADER,
    EVENT_VERSION,
    OUTBOX_ID_HEADER,
    OutboxEventCodec,
)
from application.payments.events import PAYMENT_CREATED
from application.records import OutboxRecord, OutboxStatus


def test_payment_id_prefers_envelope_payload() -> None:
    codec = OutboxEventCodec()
    body = {
        "payment_id": "ignored",
        "payload": {"payment_id": "from-payload"},
    }
    assert codec.extract_payment_id(body) == "from-payload"


def test_payment_id_falls_back_to_top_level() -> None:
    codec = OutboxEventCodec()
    assert codec.extract_payment_id({"payment_id": "top"}) == "top"


def test_payment_id_missing_or_blank_is_none() -> None:
    codec = OutboxEventCodec()
    assert codec.extract_payment_id({}) is None
    assert codec.extract_payment_id({"payment_id": "  "}) is None
    assert codec.extract_payment_id({"payload": {}}) is None


def test_payment_id_decodes_bytes() -> None:
    codec = OutboxEventCodec()
    assert codec.extract_payment_id({"payment_id": b"from-bytes"}) == "from-bytes"


def test_outbox_id_reads_header_when_body_omits_it() -> None:
    codec = OutboxEventCodec()
    outbox_id = uuid4()
    parsed = codec.extract_outbox_id({}, {OUTBOX_ID_HEADER: str(outbox_id)})
    assert parsed == outbox_id


def test_outbox_id_rejects_invalid_values() -> None:
    codec = OutboxEventCodec()
    assert codec.extract_outbox_id({"outbox_id": "not-a-uuid"}, None) is None
    assert codec.extract_outbox_id({}, None) is None


def _record(payload: dict) -> OutboxRecord:
    return OutboxRecord(
        id=uuid4(),
        event_type=PAYMENT_CREATED,
        payload=payload,
        created_at=datetime(2026, 8, 18, tzinfo=UTC),
        status=OutboxStatus.NEW,
        retry_count=0,
        published_at=None,
        claimed_at=None,
        available_at=None,
    )


def test_encode_has_required_schema_and_headers() -> None:
    record = _record({"payment_id": "x", "amount": "10.00"})
    body, headers = OutboxEventCodec().encode(record)
    decoded = json.loads(body.decode("utf-8"))
    assert set(decoded) == {
        "outbox_id",
        "event_type",
        "event_version",
        "payload",
    }
    assert decoded["outbox_id"] == str(record.id)
    assert decoded["event_type"] == PAYMENT_CREATED
    assert decoded["event_version"] == EVENT_VERSION
    assert decoded["payload"] == {"payment_id": "x", "amount": "10.00"}
    assert headers[OUTBOX_ID_HEADER] == str(record.id)
    assert headers[EVENT_TYPE_HEADER] == PAYMENT_CREATED


def test_encode_large_payload() -> None:
    record = _record({"payment_id": "x", "blob": "a" * 200_000})
    body, headers = OutboxEventCodec().encode(record)
    decoded = json.loads(body)
    assert len(decoded["payload"]["blob"]) == 200_000
    assert headers[OUTBOX_ID_HEADER] == str(record.id)
