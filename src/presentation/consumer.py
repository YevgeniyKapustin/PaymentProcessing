from __future__ import annotations

from typing import Self

from faststream import FastStream

from runtime import Runtime
from presentation.base import Entrypoint
from infrastructure.messaging.consumer import FastStreamAppFactory
from infrastructure.messaging.topology import PaymentsTopology
from presentation.amqp.dispatcher import PaymentMessageDispatcher
from presentation.amqp.subscriber import PaymentQueueSubscriber


class PaymentConsumer(Entrypoint):
    service = "payment-consumer"

    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._register_handlers()
        self.app = FastStreamAppFactory().create(
            runtime.resources.broker,
            on_startup=self.start,
            after_shutdown=self.close,
        )

    @classmethod
    def from_env(cls) -> Self:
        return cls(cls.runtime_from_env(owns_broker=False))

    def _register_handlers(self) -> None:
        topology = PaymentsTopology()
        dispatcher = PaymentMessageDispatcher(
            self._runtime.use_cases.process_payment,
            self._runtime.publisher,
        )
        PaymentQueueSubscriber(dispatcher).register(
            self._runtime.resources.broker,
            queue=topology.new_queue,
            exchange=topology.exchange,
        )

    async def start(self) -> None:
        await self._runtime.start()

    async def close(self) -> None:
        await self._runtime.close()


def create_app() -> FastStream:
    return PaymentConsumer.from_env().app
