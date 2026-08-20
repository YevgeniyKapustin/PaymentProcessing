from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class WorkerLoop:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self, run: Callable[[], Awaitable[None]]) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._guard(run))
        self._task.add_done_callback(self._consume_done)

    async def stop(self) -> None:
        self._stop.set()
        await self._join()

    def is_stopped(self) -> bool:
        return self._stop.is_set()

    async def wait(self, timeout: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=timeout)

    async def isolate(
        self,
        action: Callable[[], Awaitable[T]],
        *,
        error_event: str,
    ) -> T | None:
        try:
            return await action()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(error_event)
            return None

    async def _guard(self, run: Callable[[], Awaitable[None]]) -> None:
        try:
            await run()
        except asyncio.CancelledError:
            log.debug("worker loop cancelled")
            raise

    async def _join(self) -> None:
        task = self._task
        if task is None:
            return
        try:
            await task
        except asyncio.CancelledError:
            if self._is_caller_cancelled():
                raise
        finally:
            if task.done():
                self._task = None

    @staticmethod
    def _is_caller_cancelled() -> bool:
        caller = asyncio.current_task()
        return caller is not None and caller.cancelling() > 0

    @staticmethod
    def _consume_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        task.exception()
