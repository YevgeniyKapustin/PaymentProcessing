import json
import logging
from collections.abc import Iterator
from io import StringIO

import pytest

from infrastructure.observability.logging import LoggingConfigurator
from presentation.log_context import log_context


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def test_json_log_includes_context_and_service() -> None:
    stream = StringIO()
    LoggingConfigurator().configure(
        level="INFO",
        json_logs=True,
        service="payment-api",
        stream=stream,
    )
    with log_context(request_id="req-1"):
        logging.getLogger("sample").info("hello", extra={"payment_id": "p1"})
    payload = json.loads(stream.getvalue())
    assert payload["event"] == "hello"
    assert payload["request_id"] == "req-1"
    assert payload["payment_id"] == "p1"
    assert payload["service"] == "payment-api"
    assert payload["level"] == "info"
    assert "timestamp" in payload
    assert payload["logger"] == "sample"


def test_invalid_level_falls_back_to_info() -> None:
    stream = StringIO()
    LoggingConfigurator().configure(
        level="nope",
        json_logs=True,
        service="test",
        stream=stream,
    )
    logging.getLogger("sample").debug("hidden")
    logging.getLogger("sample").info("visible")
    payload = json.loads(stream.getvalue())
    assert payload["event"] == "visible"


def test_console_renderer_is_used_when_json_disabled() -> None:
    stream = StringIO()
    LoggingConfigurator().configure(
        level="INFO",
        json_logs=False,
        service="test",
        stream=stream,
    )
    logging.getLogger("sample").info("hello")
    output = stream.getvalue()
    assert "hello" in output
    assert not output.lstrip().startswith("{")
