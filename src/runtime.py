from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType

from application.outbox.metrics import NullOutboxMetrics
from application.ports import Clock, OutboxMetrics, PaymentGateway, Publisher
from application.use_cases.create_payment import CreatePayment
from application.use_cases.get_payment import GetPayment
from application.use_cases.process_payment import ProcessPayment
from application.use_cases.publish_outbox import PublishOutbox
from infrastructure.config import Settings
from infrastructure.resources import Resources


@dataclass(frozen=True, slots=True)
class UseCases:
    create_payment: CreatePayment
    get_payment: GetPayment
    process_payment: ProcessPayment
    publish_outbox: PublishOutbox


def _empty_metrics_text() -> str:
    return ""


@dataclass
class Runtime:
    settings: Settings
    use_cases: UseCases
    publisher: Publisher
    gateway: PaymentGateway
    clock: Clock
    resources: Resources
    metrics: OutboxMetrics = field(default_factory=NullOutboxMetrics)
    render_metrics: Callable[[], str] = field(default=_empty_metrics_text)

    async def __aenter__(self) -> Runtime:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self) -> None:
        await self.resources.start()

    async def close(self) -> None:
        await self.resources.close()
