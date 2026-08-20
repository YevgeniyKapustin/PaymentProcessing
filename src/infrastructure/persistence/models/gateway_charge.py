from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.persistence.models.base import Base


class GatewayChargeModel(Base):
    __tablename__ = "gateway_charges"

    payment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    is_successful: Mapped[bool] = mapped_column("succeeded", Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
