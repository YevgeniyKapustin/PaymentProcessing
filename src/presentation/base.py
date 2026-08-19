from __future__ import annotations

from factory import RuntimeFactory
from runtime import Runtime
from infrastructure.config import Settings
from infrastructure.observability.logging import LoggingConfigurator


class Entrypoint:
    service: str

    @classmethod
    def configure_logging(cls, settings: Settings) -> None:
        LoggingConfigurator().configure(
            level=settings.log_level,
            json_logs=settings.log_json,
            service=cls.service,
        )

    @classmethod
    def runtime_from_env(cls, *, owns_broker: bool = True) -> Runtime:
        settings = Settings.from_env()
        cls.configure_logging(settings)
        return RuntimeFactory(
            settings=settings,
            owns_broker=owns_broker,
        ).build()
