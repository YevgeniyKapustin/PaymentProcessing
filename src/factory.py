from __future__ import annotations

from functools import partial

from application.ports import Clock, OutboxMetrics, PaymentGateway, Publisher
from application.uow import UowFactory
from application.use_cases.create_payment import CreatePayment
from application.use_cases.get_payment import GetPayment
from application.use_cases.process_payment import ProcessPayment
from application.use_cases.publish_outbox import PublishOutbox
from runtime import Runtime, UseCases
from infrastructure.clock import SystemClock
from infrastructure.config import Settings
from infrastructure.gateway.random_emulator import RandomPaymentGateway
from infrastructure.gateway.sql_cache import SqlGatewayResultCache
from infrastructure.messaging.broker import RabbitBrokerFactory
from infrastructure.messaging.publisher import FastStreamPublisher
from infrastructure.messaging.topology import PaymentsTopology
from infrastructure.observability.metrics import PrometheusOutboxMetrics
from infrastructure.persistence.db import PostgresDatabase
from infrastructure.persistence.uow import SqlAlchemyUnitOfWork
from infrastructure.resources import Resources
from infrastructure.webhooks.client import HttpxWebhookClientFactory
from infrastructure.webhooks.httpx_sender import HttpxWebhookSender


class RuntimeFactory:
    def __init__(
        self,
        settings: Settings | None = None,
        clock: Clock | None = None,
        gateway: PaymentGateway | None = None,
        *,
        owns_broker: bool = True,
    ) -> None:
        self._settings = settings or Settings.from_env()
        self._clock = clock or SystemClock()
        self._gateway = gateway
        self._owns_broker = owns_broker

    def build(self) -> Runtime:
        database = PostgresDatabase(self._settings.database_url)
        resources = self._create_resources(database)
        session_factory = database.create_session_factory(resources.engine)
        uow_factory: UowFactory = partial(SqlAlchemyUnitOfWork, session_factory)
        publisher = FastStreamPublisher(
            resources.broker,
            PaymentsTopology.exchange,
        )
        metrics = PrometheusOutboxMetrics()
        gateway = self._gateway or RandomPaymentGateway(
            cache=SqlGatewayResultCache(session_factory, self._clock),
        )
        return Runtime(
            settings=self._settings,
            use_cases=self._create_use_cases(
                uow_factory,
                publisher,
                resources,
                metrics,
                gateway,
            ),
            publisher=publisher,
            resources=resources,
            metrics=metrics,
            render_metrics=metrics.render,
        )

    def _create_resources(self, database: PostgresDatabase) -> Resources:
        settings = self._settings
        http_client = HttpxWebhookClientFactory(
            timeout_seconds=settings.webhook_timeout_seconds,
            max_connections=settings.webhook_max_connections,
            max_keepalive=settings.webhook_max_keepalive,
        ).create()
        return Resources(
            engine=database.create_engine(),
            http_client=http_client,
            broker=RabbitBrokerFactory(settings.rabbitmq_url).create(),
            owns_broker=self._owns_broker,
        )

    def _create_use_cases(
        self,
        uow_factory: UowFactory,
        publisher: Publisher,
        resources: Resources,
        metrics: OutboxMetrics,
        gateway: PaymentGateway,
    ) -> UseCases:
        settings = self._settings
        return UseCases(
            create_payment=CreatePayment(uow_factory, self._clock),
            get_payment=GetPayment(uow_factory),
            process_payment=ProcessPayment(
                uow_factory,
                gateway,
                HttpxWebhookSender(resources.http_client),
                self._clock,
            ),
            publish_outbox=PublishOutbox(
                uow_factory,
                publisher,
                self._clock,
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_publish_attempts,
                claim_timeout_seconds=settings.outbox_claim_timeout_seconds,
                retention_days=settings.outbox_retention_days,
                retry_initial_seconds=settings.outbox_retry_initial_seconds,
                retry_cap_seconds=settings.outbox_retry_cap_seconds,
                metrics=metrics,
            ),
        )
