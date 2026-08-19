import asyncio
import logging

import pytest

from presentation.backoff import ExponentialBackoff
from presentation.outbox_relay import OutboxRelay


class RecordingOutbox:
    def __init__(self, results: list[int] | None = None) -> None:
        self.calls = 0
        self._results = list(results or [])
        self._default = 0

    async def execute(self) -> int:
        self.calls += 1
        if self._results:
            return self._results.pop(0)
        return self._default


@pytest.mark.asyncio
async def test_restart_after_stop_polls_again() -> None:
    outbox = RecordingOutbox()
    relay = OutboxRelay(outbox, interval=0.01)
    relay.start()
    await asyncio.sleep(0.02)
    await relay.stop()
    first = outbox.calls
    assert first > 0
    relay.start()
    await asyncio.sleep(0.02)
    await relay.stop()
    assert outbox.calls > first


@pytest.mark.asyncio
async def test_empty_poll_waits_for_stop() -> None:
    started = asyncio.Event()

    class WaitingOutbox:
        async def execute(self) -> int:
            started.set()
            return 0

    relay = OutboxRelay(WaitingOutbox(), interval=5)
    relay.start()
    await started.wait()
    await asyncio.sleep(0.02)
    await asyncio.wait_for(relay.stop(), timeout=1)


@pytest.mark.asyncio
async def test_error_is_logged_and_loop_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FlakyOutbox:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self) -> int:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("broker down")
            return 0

    outbox = FlakyOutbox()
    relay = OutboxRelay(outbox, interval=0.01, backoff=ExponentialBackoff(0.01))
    relay.start()
    with caplog.at_level(logging.ERROR):
        while outbox.calls < 2:
            await asyncio.sleep(0)
        await asyncio.wait_for(relay.stop(), timeout=1)
    assert outbox.calls >= 2
    assert "outbox relay failed" in caplog.text


@pytest.mark.asyncio
async def test_full_batch_does_not_wait_interval() -> None:
    class BusyOutbox:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self) -> int:
            self.calls += 1
            if self.calls >= 3:
                return 0
            return 10

    outbox = BusyOutbox()
    relay = OutboxRelay(outbox, interval=30, batch_size=10)
    relay.start()
    while outbox.calls < 3:
        await asyncio.sleep(0)
    await asyncio.wait_for(relay.stop(), timeout=1)
    assert outbox.calls >= 3


@pytest.mark.asyncio
async def test_stop_lets_in_flight_execute_finish() -> None:
    started = asyncio.Event()
    finished = asyncio.Event()

    class SlowOutbox:
        async def execute(self) -> int:
            started.set()
            await asyncio.sleep(0.05)
            finished.set()
            return 0

    relay = OutboxRelay(SlowOutbox(), interval=5)
    relay.start()
    await started.wait()
    await relay.stop()
    assert finished.is_set()


@pytest.mark.asyncio
async def test_stop_interrupts_busy_backlog() -> None:
    class BusyOutbox:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self) -> int:
            self.calls += 1
            return 1

    outbox = BusyOutbox()
    relay = OutboxRelay(outbox, interval=30, batch_size=1)
    relay.start()
    await asyncio.sleep(0)
    await asyncio.wait_for(relay.stop(), timeout=1)
    calls_after_stop = outbox.calls
    await asyncio.sleep(0)
    assert calls_after_stop > 0
    assert outbox.calls == calls_after_stop


@pytest.mark.asyncio
async def test_stop_handles_cancelled_task() -> None:
    started = asyncio.Event()

    class BlockingOutbox:
        async def execute(self) -> int:
            started.set()
            await asyncio.Event().wait()
            return 0

    relay = OutboxRelay(BlockingOutbox(), interval=5)
    relay.start()
    await started.wait()
    assert relay._loop._task is not None
    relay._loop._task.cancel()
    await asyncio.wait_for(relay.stop(), timeout=1)


@pytest.mark.asyncio
async def test_repeated_errors_back_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenOutbox:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self) -> int:
            self.calls += 1
            raise RuntimeError("broker down")

    outbox = BrokenOutbox()
    relay = OutboxRelay(outbox, interval=0.01)
    relay.start()
    with caplog.at_level(logging.ERROR):
        await asyncio.sleep(0.05)
        await asyncio.wait_for(relay.stop(), timeout=1)
    assert outbox.calls == 1
    assert "outbox relay failed" in caplog.text


@pytest.mark.asyncio
async def test_partial_batch_waits_for_interval() -> None:
    class TrickleOutbox:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self) -> int:
            self.calls += 1
            return 1

    outbox = TrickleOutbox()
    relay = OutboxRelay(outbox, interval=0.05, batch_size=50)
    relay.start()
    await asyncio.sleep(0.02)
    await asyncio.wait_for(relay.stop(), timeout=1)
    assert outbox.calls == 1
