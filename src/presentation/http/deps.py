from __future__ import annotations

from typing import Annotated

from fastapi import Header, Request

from application.use_cases.create_payment import CreatePayment
from application.use_cases.get_payment import GetPayment
from presentation.http.auth import ApiKeyAuthenticator

_authenticator = ApiKeyAuthenticator()


def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    _authenticator.verify(x_api_key, request.app.state.api_key)


def get_create_payment(request: Request) -> CreatePayment:
    return request.app.state.create_payment


def get_payment_use_case(request: Request) -> GetPayment:
    return request.app.state.get_payment
