import asyncio

import pytest
from pytest import MonkeyPatch

from presentation.backoff import ExponentialBackoff
from presentation.worker import WorkerLoop


def test_delay_doubles_until_cap() -> None:
    backoff = ExponentialBackoff(1.0, cap=8.0, jitter=False)
    assert backoff.next_delay() == 1.0
    assert backoff.next_delay() == 2.0
    assert backoff.next_delay() == 4.0
    assert backoff.next_delay() == 8.0
    assert backoff.next_delay() == 8.0


def test_reset_restarts_from_initial() -> None:
    backoff = ExponentialBackoff(1.0, cap=8.0, jitter=False)
    backoff.next_delay()
    backoff.next_delay()
    backoff.reset()
    assert backoff.next_delay() == 1.0


def test_for_interval_floors_short_polls() -> None:
    assert ExponentialBackoff.for_interval(0.01, jitter=False).next_delay() == 1.0
    assert ExponentialBackoff.for_interval(5.0, jitter=False).next_delay() == 5.0


def test_jitter_uses_shared_delay_seconds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("application.retry.backoff.random.random", lambda: 0.0)
    backoff = ExponentialBackoff(2.0, cap=8.0, jitter=True)
    assert backoff.next_delay() == 1.0


@pytest.mark.asyncio
async def test_can_restart_after_stop() -> None:
    starts = 0
    loop = WorkerLoop()

    async def run() -> None:
        nonlocal starts
        starts += 1
        while not loop.stopped():
            await loop.idle(60)

    loop.start(run)
    await asyncio.wait_for(loop.stop(), timeout=1)
    loop.start(run)
    await asyncio.wait_for(loop.stop(), timeout=1)
    assert starts == 2
    assert loop._task is None


@pytest.mark.asyncio
async def test_start_while_running_is_noop() -> None:
    starts = 0
    loop = WorkerLoop()

    async def run() -> None:
        nonlocal starts
        starts += 1
        while not loop.stopped():
            await loop.idle(60)

    loop.start(run)
    loop.start(run)
    await asyncio.wait_for(loop.stop(), timeout=1)
    assert starts == 1


@pytest.mark.asyncio
async def test_stop_after_worker_cancelled_does_not_raise() -> None:
    started = asyncio.Event()
    loop = WorkerLoop()

    async def run() -> None:
        started.set()
        await asyncio.Event().wait()

    loop.start(run)
    await started.wait()
    assert loop._task is not None
    loop._task.cancel()
    await asyncio.wait_for(loop.stop(), timeout=1)
    assert loop._task is None


@pytest.mark.asyncio
async def test_stop_propagates_caller_cancellation() -> None:
    started = asyncio.Event()
    loop = WorkerLoop()

    async def run() -> None:
        started.set()
        await asyncio.sleep(60)

    loop.start(run)
    await started.wait()
    stop_task = asyncio.create_task(loop.stop())
    await asyncio.sleep(0)
    stop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop_task
    assert loop._task is None
