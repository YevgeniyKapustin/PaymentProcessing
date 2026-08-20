from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from presentation.http.access import REQUEST_ID_HEADER
from presentation.http.policy import AccessLogPolicy
from presentation.log_context import RequestId
from tests.presentation.http.test_payments_api import API_KEY, BODY, HEADERS, _app


def test_resolve_request_id_keeps_valid_header() -> None:
    assert RequestId().resolve("abc-123") == "abc-123"


def test_resolve_request_id_rejects_garbage() -> None:
    generated = RequestId().resolve("\x00not-ok")
    assert generated != "\x00not-ok"
    assert len(generated) == 36


def test_choose_log_level_for_status() -> None:
    policy = AccessLogPolicy()
    assert policy.choose_log_level(200) == logging.INFO
    assert policy.choose_log_level(404) == logging.WARNING
    assert policy.choose_log_level(500) == logging.ERROR


def test_health_success_is_not_access_logged() -> None:
    policy = AccessLogPolicy()
    assert policy.should_log("/health", 200) is False
    assert policy.should_log("/ready", 200) is False
    assert policy.should_log("/health", 500) is True
    assert policy.should_log("/api/v1/payments", 202) is True


@pytest.mark.asyncio
async def test_request_id_is_echoed() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={REQUEST_ID_HEADER: "trace-1"},
        )
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "trace-1"


@pytest.mark.asyncio
async def test_request_id_is_generated_when_missing() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_health_is_not_logged_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = ASGITransport(app=_app())
    with caplog.at_level(logging.INFO):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/health")
    assert "http.request" not in caplog.text


@pytest.mark.asyncio
async def test_unauthorized_is_logged_as_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payment_id = uuid4()
    path = f"/api/v1/payments/{payment_id}"
    transport = ASGITransport(app=_app())
    with caplog.at_level(logging.WARNING):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(path)
    assert response.status_code == 401
    records = [item for item in caplog.records if item.message == "http.request"]
    assert records
    record = records[-1]
    assert record.levelno == logging.WARNING
    assert record.status_code == 401
    assert record.method == "GET"
    assert record.path == path


@pytest.mark.asyncio
async def test_unhandled_error_returns_500_with_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    transport = ASGITransport(app=app)
    with caplog.at_level(logging.ERROR):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/boom")
    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER]
    assert response.json() == {"detail": "Internal Server Error"}
    assert "http.request" in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_create_payment_logs_business_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = ASGITransport(app=_app())
    with caplog.at_level(logging.INFO):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/payments",
                json=BODY,
                headers=HEADERS,
            )
    assert response.status_code == 202
    records = [item for item in caplog.records if item.message == "payment.accepted"]
    assert records
    assert records[-1].payment_id == response.json()["payment_id"]
    assert records[-1].status == "pending"
    assert API_KEY not in caplog.text
