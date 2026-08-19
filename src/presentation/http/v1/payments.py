from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from application.use_cases.create_payment import CreatePayment
from application.use_cases.get_payment import GetPayment
from presentation.http.deps import (
    get_create_payment,
    get_payment_use_case,
    require_api_key,
)
from presentation.http.v1.schemas import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PaymentResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreatePaymentResponse,
)
async def create_payment(
    body: CreatePaymentRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    use_case: Annotated[CreatePayment, Depends(get_create_payment)],
) -> CreatePaymentResponse:
    result = await use_case.execute(body.to_input(idempotency_key))
    log.info(
        "payment.accepted",
        extra={"payment_id": str(result.payment_id), "status": result.status},
    )
    return CreatePaymentResponse(
        payment_id=result.payment_id,
        status=result.status,
        created_at=result.created_at,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    use_case: Annotated[GetPayment, Depends(get_payment_use_case)],
) -> PaymentResponse:
    result = await use_case.execute(payment_id)
    return PaymentResponse.model_validate(result)
