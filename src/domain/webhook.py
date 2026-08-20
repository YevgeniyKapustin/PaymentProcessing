from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from domain.exceptions import InvalidWebhookUrlError

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
    }
)


@dataclass(frozen=True, slots=True)
class WebhookUrl:
    value: str

    def __post_init__(self) -> None:
        parsed = urlparse(self.value)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise InvalidWebhookUrlError("webhook url must be http or https")
        if parsed.username or parsed.password:
            raise InvalidWebhookUrlError("webhook url must not include credentials")
        host = parsed.hostname
        if not host:
            raise InvalidWebhookUrlError("webhook url host is required")
        host = host.lower().rstrip(".")
        if _is_blocked_host(host) or _is_blocked_ip(host):
            raise InvalidWebhookUrlError("webhook url must not target a private host")


def _is_blocked_host(host: str) -> bool:
    if host in _BLOCKED_HOSTS:
        return True
    return host.endswith((".localhost", ".local", ".internal"))


def _is_blocked_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global
