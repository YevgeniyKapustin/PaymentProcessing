import importlib
from unittest.mock import MagicMock

import pytest

from runtime import Runtime, UseCases
from presentation.api import PaymentApi
from presentation.consumer import PaymentConsumer
from infrastructure.config import Settings
from infrastructure.resources import Resources


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        rabbitmq_url="amqp://guest:guest@localhost/",
        api_key="test",
        log_level="DEBUG",
        use_json_logs=False,
    )


def _runtime() -> Runtime:
    return Runtime(
        settings=_settings(),
        use_cases=UseCases(
            create_payment=MagicMock(),
            get_payment=MagicMock(),
            process_payment=MagicMock(),
            publish_outbox=MagicMock(),
        ),
        publisher=MagicMock(),
        resources=Resources(
            engine=MagicMock(),
            http_client=MagicMock(),
            broker=MagicMock(),
        ),
    )


def test_runtime_from_env_configures_logging_before_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    captured: dict[str, object] = {}

    def fake_configure_logging(**kwargs: object) -> None:
        order.append("logging")
        captured["logging"] = kwargs

    class FakeFactory:
        def __init__(
            self,
            settings: Settings | None = None,
            **kwargs: object,
        ) -> None:
            captured["settings"] = settings
            captured["owns_broker"] = kwargs.get("owns_broker", True)

        def build(self) -> Runtime:
            order.append("build")
            return _runtime()

    class FakeConfigurator:
        def configure(self, **kwargs: object) -> None:
            fake_configure_logging(**kwargs)

    monkeypatch.setattr("presentation.base.LoggingConfigurator", FakeConfigurator)
    monkeypatch.setattr("presentation.base.RuntimeFactory", FakeFactory)
    monkeypatch.setattr(
        "presentation.base.Settings.from_env",
        classmethod(lambda cls: _settings()),
    )
    PaymentConsumer.runtime_from_env(owns_broker=False)
    assert order == ["logging", "build"]
    assert captured["owns_broker"] is False
    assert captured["logging"]["service"] == "payment-consumer"
    assert captured["logging"]["level"] == "DEBUG"
    assert captured["logging"]["use_json_logs"] is False
    PaymentApi.runtime_from_env()
    assert captured["owns_broker"] is True
    assert captured["logging"]["service"] == "payment-api"


@pytest.mark.parametrize(
    ("module_name", "cls_name"),
    [
        ("presentation.api", "PaymentApi"),
        ("presentation.consumer", "PaymentConsumer"),
        ("presentation.publisher", "OutboxPublisher"),
    ],
)
def test_create_app_builds_from_env(
    module_name: str,
    cls_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(module_name)
    cls = getattr(module, cls_name)
    fake = MagicMock()
    fake.app = object()
    monkeypatch.setattr(cls, "from_env", classmethod(lambda factory_cls: fake))
    assert module.create_app() is fake.app
