from uuid import uuid4

from application.outbox.codec import OUTBOX_ID_HEADER, OutboxEventCodec


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
