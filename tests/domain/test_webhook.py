import pytest

from domain.exceptions import InvalidWebhookUrlError
from domain.webhook import WebhookUrl

PUBLIC = "https://example.com/hook"


@pytest.mark.parametrize(
    "url",
    [
        PUBLIC,
        "http://example.com/hook",
        "https://httpbingo.org/status/204",
        "https://1.1.1.1/hook",
    ],
)
def test_public_http_urls_are_accepted(url: str) -> None:
    assert WebhookUrl(url).value == url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "file:///etc/passwd",
        "https://user:pass@example.com/hook",
        "https:///no-host",
        "http://localhost/hook",
        "http://localhost.localdomain/hook",
        "http://foo.localhost/hook",
        "http://printer.local/hook",
        "http://svc.internal/hook",
        "http://metadata.google.internal/",
        "http://127.0.0.1/hook",
        "http://10.0.0.1/hook",
        "http://172.16.0.1/hook",
        "http://192.168.1.1/hook",
        "http://169.254.169.254/",
        "http://[::1]/hook",
        "not-a-url",
    ],
)
def test_private_or_invalid_urls_are_rejected(url: str) -> None:
    with pytest.raises(InvalidWebhookUrlError):
        WebhookUrl(url)
