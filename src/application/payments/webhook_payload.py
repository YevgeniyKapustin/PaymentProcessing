from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.payment import Payment


class WebhookPayloadBuilder:
    def build(self, payment: Payment) -> dict[str, Any]:
        processed_at: datetime | None = payment.processed_at
        return {
            "payment_id": str(payment.id.value),
            "status": payment.status.value,
            "amount": str(payment.money.amount),
            "currency": payment.money.currency.value,
            "processed_at": processed_at.isoformat() if processed_at else None,
        }
