from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from domain.exceptions import InvalidCurrencyError, InvalidMoneyError

_QUANT = Decimal("0.01")


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"

    @classmethod
    def parse(cls, currency: Currency | str) -> Currency:
        if isinstance(currency, cls):
            return currency
        try:
            return cls(currency)
        except ValueError as exc:
            raise InvalidCurrencyError(f"unsupported currency: {currency}") from exc


class Money:
    __slots__ = ("_amount", "_currency")

    def __init__(self, amount: Decimal, currency: Currency | str) -> None:
        if isinstance(amount, bool) or isinstance(amount, float):
            raise InvalidMoneyError("amount must be Decimal, never float")
        if isinstance(amount, int):
            amount = Decimal(amount)
        if not isinstance(amount, Decimal):
            raise InvalidMoneyError("amount must be Decimal")
        if not amount.is_finite():
            raise InvalidMoneyError("amount must be finite")
        if amount <= 0:
            raise InvalidMoneyError("amount must be greater than zero")
        exponent = amount.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise InvalidMoneyError("amount scale must be at most 2")
        self._amount = amount.quantize(_QUANT)
        self._currency = Currency.parse(currency)

    @property
    def amount(self) -> Decimal:
        return self._amount

    @property
    def currency(self) -> Currency:
        return self._currency

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._amount == other._amount and self._currency is other._currency

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))
