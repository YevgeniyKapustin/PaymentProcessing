# Payment Service

Hexagon: FastAPI / FastStream adapters call use cases through ports.
Use cases mutate the `Payment` aggregate and write the outbox in one UoW.
Postgres, RabbitMQ, httpx, and the gateway emulator sit behind outbound ports.
`src/factory.py` is the only module that wires concrete classes.

POST never publishes to RabbitMQ. A dedicated publisher process relays
unpublished outbox rows with confirms, then sets `published_at`. Scrape
`/metrics` on that process (`:8001`), not on the API.
The consumer is idempotent because `succeed()` / `fail()` are no-ops on a
terminal payment. Webhooks are at-least-once: the inbox row is written after
a successful POST, so a crash in between redelivers. Receivers should key on
`Idempotency-Key` (the payment id). Transient webhook/gateway errors get 3
attempts with exponential TTL (`1s`, then `2s`) and then land on
`payments.new.dlq`. A 4xx webhook is permanent and goes straight to the DLQ.
Private, loopback, and link-local `webhook_url` values are rejected (422 / DLQ).
If the handler dies before it can forward a message, Rabbit rejects it to the
same DLQ via the `payments.new` dead-letter policy.

The random gateway emulator stores the first charge per payment id in
`gateway_charges`, so a consumer restart keeps the same 90/10 outcome.

## Run locally

You need Docker. Copy `.env.example` to `.env`, then:

```bash
docker compose up --build
```

Wait until the `api` container is healthy (`/ready` checks Postgres and
RabbitMQ). Then open:

- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/ready
- Outbox metrics: http://localhost:8001/metrics
- RabbitMQ UI: http://127.0.0.1:15672 (`guest` / `guest`)

Stop with `Ctrl+C`, or `docker compose down`.

If RabbitMQ was already running from an older compose file, recreate it
once so the new `payments.new` DLX arguments apply:

```bash
docker compose down
docker volume rm paymentprocessing_rabbitmq_data
docker compose up --build
```

## Try it in the browser

All of this is Swagger at http://localhost:8000/docs. The fake gateway
takes 2–5 seconds and succeeds about 90% of the time, so the first GET
is usually still `pending`.

### Happy path

1. Open **POST `/api/v1/payments`** → **Try it out**.
2. Headers:
   - `X-API-Key`: `changeme`
   - `Idempotency-Key`: `demo-1` (any unique string for a new payment)
3. Body (`webhook_url` must be public `http(s)` — loopback and private
   hosts return 422; the consumer also cannot call `localhost` on your
   machine):

```json
{
  "amount": "10.00",
  "currency": "USD",
  "description": "test",
  "metadata": {},
  "webhook_url": "https://httpbingo.org/status/204"
}
```

4. **Execute**. You should get **202** with `status: pending` and a
   `payment_id`. Copy that id.
5. Open **GET `/api/v1/payments/{payment_id}`** → **Try it out**.
   Paste the id, same `X-API-Key`, **Execute**. Wait a few seconds and
   run it again until `succeeded` or `failed`.

### Same request twice

Execute POST again with the same `Idempotency-Key` and the same body.
You still get **202** and the **same** `payment_id`.

Change `amount` to `20.00`, keep the same key, Execute: **409**.

### Auth

Clear `X-API-Key` and Execute POST: **401**.
`/health` and `/ready` still work without a key.

Set `webhook_url` to `http://127.0.0.1/hook`: **422**.

### Dead letter (poison webhook)

New `Idempotency-Key`, set `webhook_url` to
`https://httpbingo.org/status/400`, Execute.

Charge still runs, so GET may show `succeeded`/`failed`. The message
goes straight to queue `payments.new.dlq` (RabbitMQ UI → Queues).

For retries then DLQ, use `https://httpbingo.org/status/503`. Watch
`payments.new.retry` bump, then `payments.new.dlq` after ~1s then ~2s.
