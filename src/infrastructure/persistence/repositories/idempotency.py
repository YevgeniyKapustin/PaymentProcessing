from __future__ import annotations

from sqlalchemy.exc import IntegrityError


class IdempotencyConstraint:
    def matches(self, exc: IntegrityError) -> bool:
        orig = exc.orig
        constraint = ""
        if orig is not None:
            constraint = str(getattr(orig, "constraint_name", "") or "")
        if "idempotency" in constraint.lower():
            return True
        text = str(orig).lower() if orig is not None else str(exc).lower()
        return "idempotency_key" in text or "uq_payments_idempotency_key" in text
