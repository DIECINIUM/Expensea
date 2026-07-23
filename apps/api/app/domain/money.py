"""Exact monetary boundary helpers."""

import re
from decimal import Decimal

from app.db.base import MONEY_PRECISION, MONEY_SCALE

_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_MAX_ABSOLUTE_AMOUNT = Decimal(10) ** (MONEY_PRECISION - MONEY_SCALE)


def normalize_currency_code(value: str) -> str:
    """Normalize and validate the persisted ISO-4217-shaped currency code."""
    normalized = value.strip().upper()
    if _CURRENCY_PATTERN.fullmatch(normalized) is None:
        msg = "Currency must be a three-letter uppercase code"
        raise ValueError(msg)
    return normalized


def validate_positive_money(value: Decimal) -> Decimal:
    """Reject values PostgreSQL would round or overflow as NUMERIC(19, 4)."""
    if not value.is_finite():
        msg = "Amount must be finite"
        raise ValueError(msg)
    if value <= 0:
        msg = "Amount must be greater than zero"
        raise ValueError(msg)
    if value >= _MAX_ABSOLUTE_AMOUNT:
        msg = "Amount exceeds NUMERIC(19, 4)"
        raise ValueError(msg)

    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    if not isinstance(exponent, int):
        msg = "Amount must be finite"
        raise ValueError(msg)
    fractional_digits = max(-exponent, 0)
    if fractional_digits > MONEY_SCALE:
        msg = f"Amount cannot have more than {MONEY_SCALE} fractional digits"
        raise ValueError(msg)
    return value
