import asyncio

import pytest

from application.exceptions import (
    PermanentProcessingError,
    TransientDependencyError,
    wrap_as_transient,
)


def test_wrap_as_transient_reraises_transient() -> None:
    with pytest.raises(TransientDependencyError, match="busy"):
        with wrap_as_transient("wrapped"):
            raise TransientDependencyError("busy")


def test_wrap_as_transient_reraises_permanent() -> None:
    with pytest.raises(PermanentProcessingError, match="declined"):
        with wrap_as_transient("wrapped"):
            raise PermanentProcessingError("declined")


def test_wrap_as_transient_wraps_unknown_errors() -> None:
    with pytest.raises(TransientDependencyError, match="wrapped") as caught:
        with wrap_as_transient("wrapped"):
            raise RuntimeError("boom")
    assert isinstance(caught.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_wrap_as_transient_wraps_errors_raised_from_await() -> None:
    async def boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(TransientDependencyError, match="wrapped") as caught:
        with wrap_as_transient("wrapped"):
            await boom()
    assert isinstance(caught.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_wrap_as_transient_does_not_wrap_cancellation() -> None:
    async def cancelled() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        with wrap_as_transient("wrapped"):
            await cancelled()
