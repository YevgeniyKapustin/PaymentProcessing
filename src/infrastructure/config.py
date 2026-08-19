from __future__ import annotations

from typing import Self

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_url: str
    rabbitmq_url: str
    api_key: str
    webhook_timeout_seconds: float = 5.0
    webhook_max_connections: int = 100
    webhook_max_keepalive: int = 20
    outbox_poll_interval_seconds: float = 0.5
    outbox_batch_size: int = 50
    outbox_max_publish_attempts: int = 8
    outbox_retry_initial_seconds: float = 1.0
    outbox_retry_cap_seconds: float = 60.0
    outbox_claim_timeout_seconds: float = 60.0
    outbox_retention_days: int = 3
    log_level: str = "INFO"
    log_json: bool = True

    @classmethod
    def from_env(cls) -> Self:
        return cls()  # type: ignore[call-arg]
