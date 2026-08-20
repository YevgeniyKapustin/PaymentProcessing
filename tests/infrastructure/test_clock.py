from datetime import UTC, datetime

from infrastructure.clock import SystemClock


def test_system_clock_returns_utc_now() -> None:
    before = datetime.now(UTC)
    moment = SystemClock().now()
    after = datetime.now(UTC)
    assert moment.tzinfo is UTC
    assert before <= moment <= after
