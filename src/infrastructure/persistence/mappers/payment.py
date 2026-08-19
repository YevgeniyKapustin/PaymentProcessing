from __future__ import annotations

from domain.ids import IdempotencyKey, PaymentId
from domain.money import Currency, Money
from domain.payment import Payment, PaymentStatus
from infrastructure.persistence.models.payment import PaymentModel


class PaymentMapper:
    def apply(self, model: PaymentModel, payment: Payment) -> None:
        model.amount = payment.money.amount
        model.currency = payment.money.currency.value
        model.description = payment.description
        model.extra = payment.metadata
        model.status = payment.status.value
        model.idempotency_key = payment.idempotency_key.value
        model.webhook_url = payment.webhook_url
        model.created_at = payment.created_at
        model.processed_at = payment.processed_at

    def to_model(self, payment: Payment) -> PaymentModel:
        model = PaymentModel(id=payment.id.value)
        self.apply(model, payment)
        return model

    def to_domain(self, model: PaymentModel) -> Payment:
        return Payment.reconstitute(
            id=PaymentId(model.id),
            money=Money(model.amount, Currency(model.currency)),
            description=model.description,
            metadata=model.extra,
            status=PaymentStatus(model.status),
            idempotency_key=IdempotencyKey(model.idempotency_key),
            webhook_url=model.webhook_url,
            created_at=model.created_at,
            processed_at=model.processed_at,
        )
