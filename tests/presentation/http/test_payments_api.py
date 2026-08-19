from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from application.use_cases.create_payment import CreatePayment
from application.use_cases.get_payment import GetPayment
from infrastructure.observability.metrics import PrometheusOutboxMetrics
from presentation.http.app import HttpAppFactory
from tests.application.fakes import FrozenClock, InMemoryStore, make_uow_factory

API_KEY = "test-key"
HEADERS = {
    "X-API-Key": API_KEY,
    "Idempotency-Key": "http-1",
}
BODY = {
    "amount": "10.00",
    "currency": "USD",
    "description": "test",
    "metadata": {},
    "webhook_url": "https://example.com/webhook",
}


def _app():
    store = InMemoryStore()
    clock = FrozenClock(datetime(2026, 8, 18, tzinfo=UTC))
    factory = make_uow_factory(store)
    return HttpAppFactory().create(
        create_payment=CreatePayment(factory, clock),
        get_payment=GetPayment(factory),
        api_key=API_KEY,
    )


@pytest.mark.asyncio
async def test_create_without_api_key_is_401() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/payments",
            json=BODY,
            headers={"Idempotency-Key": "http-1"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_payment_returns_202() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/payments",
            json=BODY,
            headers=HEADERS,
        )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"
    assert "payment_id" in payload
    assert "created_at" in payload


@pytest.mark.asyncio
async def test_get_payment_after_create() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/payments",
            json=BODY,
            headers=HEADERS,
        )
        payment_id = created.json()["payment_id"]
        response = await client.get(
            f"/api/v1/payments/{payment_id}",
            headers={"X-API-Key": API_KEY},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["payment_id"] == payment_id
    assert payload["amount"] == "10.00"
    assert payload["status"] == "pending"


@pytest.mark.asyncio
async def test_get_missing_payment_is_404() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/payments/{uuid4()}",
            headers={"X-API-Key": API_KEY},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_idempotency_conflict_is_409() -> None:
    transport = ASGITransport(app=_app())
    conflict_body = {**BODY, "amount": "20.00"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/payments",
            json=BODY,
            headers=HEADERS,
        )
        second = await client.post(
            "/api/v1/payments",
            json=conflict_body,
            headers=HEADERS,
        )
    assert first.status_code == 202
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_create_with_invalid_amount_is_422() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/payments",
            json={**BODY, "amount": "-1.00"},
            headers=HEADERS,
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_invalid_currency_is_422() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/payments",
            json={**BODY, "currency": "GBP"},
            headers=HEADERS,
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_invalid_webhook_url_is_422() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/payments",
            json={**BODY, "webhook_url": "not-a-url"},
            headers=HEADERS,
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_empty_idempotency_key_is_422() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/payments",
            json=BODY,
            headers={"X-API-Key": API_KEY, "Idempotency-Key": "   "},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_metrics_exposes_outbox_gauges() -> None:
    metrics = PrometheusOutboxMetrics()
    metrics.set_queue_size(4)
    metrics.set_failed_count(2)
    metrics.record_error()
    clock = FrozenClock(datetime(2026, 8, 18, tzinfo=UTC))
    factory = make_uow_factory(InMemoryStore())
    app = HttpAppFactory().create(
        create_payment=CreatePayment(factory, clock),
        get_payment=GetPayment(factory),
        api_key=API_KEY,
        metrics_text=metrics.render,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert "outbox_queue_size 4" in response.text
    assert "outbox_failed 2" in response.text
    assert "outbox_publish_errors_total 1" in response.text


@pytest.mark.asyncio
async def test_ready_is_ok_without_probe() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_is_503_when_probe_fails() -> None:
    class Down:
        async def ready(self) -> bool:
            return False

    clock = FrozenClock(datetime(2026, 8, 18, tzinfo=UTC))
    factory = make_uow_factory(InMemoryStore())
    app = HttpAppFactory().create(
        create_payment=CreatePayment(factory, clock),
        get_payment=GetPayment(factory),
        api_key=API_KEY,
        readiness=Down(),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
