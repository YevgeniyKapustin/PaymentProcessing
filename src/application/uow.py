from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from application.ports import UnitOfWork

UowFactory = Callable[[], AbstractAsyncContextManager[UnitOfWork]]
