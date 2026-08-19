from __future__ import annotations

from faststream.rabbit import Channel, RabbitBroker


class RabbitBrokerFactory:
    def __init__(self, url: str) -> None:
        self._url = url

    def create(self) -> RabbitBroker:
        return RabbitBroker(
            self._url,
            default_channel=Channel(publisher_confirms=True),
            fail_fast=False,
        )
