import pytest
from httpx import (
    AsyncClient,
    ConnectError,
    MockTransport,
    Request,
    Response,
    TimeoutException,
)

from application.exceptions import (
    PermanentProcessingError,
    TransientDependencyError,
)
from domain.exceptions import InvalidWebhookUrlError
from infrastructure.webhooks.httpx_sender import HttpxWebhookSender


async def _send(status: int | None = None, error: Exception | None = None) -> None:
    def handler(request: Request) -> Response:
        if error is not None:
            raise error
        assert status is not None
        return Response(status)

    async with AsyncClient(transport=MockTransport(handler)) as client:
        await HttpxWebhookSender(client).send(
            "https://example.com/hook",
            {"ok": True},
            idempotency_key="pay-1",
        )


@pytest.mark.asyncio
async def test_webhook_2xx_succeeds() -> None:
    await _send(status=204)


@pytest.mark.asyncio
async def test_webhook_4xx_is_permanent() -> None:
    with pytest.raises(PermanentProcessingError):
        await _send(status=400)


@pytest.mark.asyncio
async def test_webhook_5xx_is_transient() -> None:
    with pytest.raises(TransientDependencyError):
        await _send(status=503)


@pytest.mark.asyncio
async def test_webhook_timeout_is_transient() -> None:
    with pytest.raises(TransientDependencyError, match="timeout"):
        await _send(error=TimeoutException("timeout"))


@pytest.mark.asyncio
async def test_webhook_transport_error_is_transient() -> None:
    with pytest.raises(TransientDependencyError, match="transport"):
        await _send(error=ConnectError("down"))


@pytest.mark.asyncio
async def test_private_webhook_url_is_permanent() -> None:
    def handler(request: Request) -> Response:
        raise AssertionError("must not send")

    async with AsyncClient(transport=MockTransport(handler)) as client:
        with pytest.raises(InvalidWebhookUrlError):
            await HttpxWebhookSender(client).send(
                "http://127.0.0.1/hook",
                {"ok": True},
                idempotency_key="pay-1",
            )


@pytest.mark.asyncio
async def test_webhook_sends_idempotency_key() -> None:
    seen: list[Request] = []

    def handler(request: Request) -> Response:
        seen.append(request)
        return Response(204)

    async with AsyncClient(transport=MockTransport(handler)) as client:
        await HttpxWebhookSender(client).send(
            "https://example.com/hook",
            {"ok": True},
            idempotency_key="pay-1",
        )
    assert seen[0].headers["idempotency-key"] == "pay-1"
