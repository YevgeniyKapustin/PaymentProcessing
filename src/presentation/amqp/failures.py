from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from application.outbox.routing import DLQ_ROUTING_KEY, RETRY_ROUTING_KEY
from application.ports import Publisher
from application.retry.policy import DispatchAction, RetryPolicy

log = logging.getLogger(__name__)

RETRY_COUNT_HEADER = "x-retry-count"


class FailureRouter:
    def __init__(
        self,
        publisher: Publisher,
        policy: RetryPolicy | None = None,
    ) -> None:
        self._publisher = publisher
        self._policy = policy or RetryPolicy()

    async def route(
        self,
        *,
        body: bytes,
        headers: Mapping[str, Any] | None,
        retry_count: int,
        error: Exception,
    ) -> None:
        action = self._policy.decide_action(retry_count, error)
        if action is DispatchAction.DLQ:
            await self._to_dlq(body, headers, retry_count, error)
            return
        await self._schedule_retry(body, headers, retry_count, error)

    async def _schedule_retry(
        self,
        body: bytes,
        headers: Mapping[str, Any] | None,
        retry_count: int,
        error: Exception,
    ) -> None:
        delay = self._policy.compute_delay_seconds(retry_count)
        next_headers = dict(headers or {})
        next_headers[RETRY_COUNT_HEADER] = retry_count + 1
        await self._publisher.publish(
            RETRY_ROUTING_KEY,
            body,
            headers=next_headers,
            expiration=delay,
        )
        log.info(
            "payment.retry_scheduled",
            extra={
                "retry_count": retry_count + 1,
                "delay_seconds": delay,
                "error_type": type(error).__name__,
            },
        )

    async def _to_dlq(
        self,
        body: bytes,
        headers: Mapping[str, Any] | None,
        retry_count: int,
        error: Exception,
    ) -> None:
        await self._publisher.publish(DLQ_ROUTING_KEY, body, headers=headers)
        log.warning(
            "payment.routed_to_dlq",
            extra={
                "retry_count": retry_count,
                "error_type": type(error).__name__,
            },
        )
