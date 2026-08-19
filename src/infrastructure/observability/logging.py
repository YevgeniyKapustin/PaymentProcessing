from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any, TextIO

import structlog
from structlog.types import Processor


class LoggingConfigurator:
    _NOISY_LOGGERS = (
        "aio_pika",
        "aiormq",
        "httpcore",
        "httpx",
        "uvicorn.access",
    )

    def configure(
        self,
        *,
        level: str = "INFO",
        json_logs: bool = True,
        service: str,
        stream: TextIO | None = None,
    ) -> None:
        self._service = service
        self._json_logs = json_logs
        self._stream = stream
        log_level = self._parse_log_level(level)
        shared = self._build_shared_processors()
        renderer = self._build_renderer()
        foreign_chain = self._configure_structlog(shared)
        self._configure_root_logger(
            shared=foreign_chain,
            renderer=renderer,
            level=log_level,
        )
        self._silence_noisy_loggers(log_level)

    def _parse_log_level(self, level: str) -> int:
        numeric = logging.getLevelName(level.upper())
        if isinstance(numeric, int):
            return numeric
        return logging.INFO

    def _add_service(
        self,
        _logger: object,
        _method: str,
        event_dict: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        event_dict.setdefault("service", self._service)
        return event_dict

    def _drop_none_values(
        self,
        _logger: object,
        _method: str,
        event_dict: MutableMapping[str, Any],
    ) -> dict[str, Any]:
        return {key: value for key, value in event_dict.items() if value is not None}

    def _build_shared_processors(self) -> list[Processor]:
        return [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ExtraAdder(),
            self._add_service,
            self._drop_none_values,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
        ]

    def _build_renderer(self) -> Processor:
        if self._json_logs:
            return structlog.processors.JSONRenderer()
        return structlog.dev.ConsoleRenderer(colors=True)

    def _configure_structlog(self, shared: list[Processor]) -> list[Processor]:
        processors = list(shared)
        if self._json_logs:
            processors.append(structlog.processors.format_exc_info)
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                *processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        return processors

    def _configure_root_logger(
        self,
        *,
        shared: list[Processor],
        renderer: Processor,
        level: int,
    ) -> None:
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
            foreign_pre_chain=shared,
        )
        handler = logging.StreamHandler(self._stream or sys.stdout)
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(level)

    def _silence_noisy_loggers(self, log_level: int) -> None:
        sqlalchemy_level = logging.DEBUG if log_level <= logging.DEBUG else logging.WARNING
        logging.getLogger("sqlalchemy.engine").setLevel(sqlalchemy_level)
        for name in self._NOISY_LOGGERS:
            library = logging.getLogger(name)
            library.handlers.clear()
            library.setLevel(logging.WARNING)
            library.propagate = name != "uvicorn.access"
            if name == "uvicorn.access":
                library.disabled = True
