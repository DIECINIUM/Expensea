"""Validated commands accepted by the ledger application service."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.domain.enums import TransactionStatus, TransactionType
from app.domain.money import normalize_currency_code, validate_positive_money
from app.domain.normalization import normalize_display_text
from app.ledger.errors import LedgerValidationError

SUPPORTED_CURRENCIES = frozenset(
    {
        "AED",
        "AUD",
        "CAD",
        "CHF",
        "CNY",
        "EUR",
        "GBP",
        "HKD",
        "INR",
        "JPY",
        "NZD",
        "SGD",
        "USD",
    }
)


@dataclass(frozen=True, slots=True)
class CreateTransactionCommand:
    """Normalized values for one manual ledger transaction."""

    amount: Decimal
    currency: str
    transaction_type: TransactionType
    description: str
    transaction_date: datetime
    status: TransactionStatus
    category_id: UUID | None


def parse_create_transaction(
    *,
    amount: str,
    currency: str,
    transaction_type: TransactionType,
    description: str,
    transaction_date: datetime,
    status: TransactionStatus = TransactionStatus.POSTED,
    category_id: UUID | None = None,
) -> CreateTransactionCommand:
    """Validate an untrusted GraphQL command without lossy coercion."""
    parsed_amount = _parse_amount(amount)
    parsed_currency = _parse_currency(currency)
    parsed_description = normalize_display_text(description)
    if not parsed_description:
        raise LedgerValidationError(
            code="INVALID_DESCRIPTION",
            message="Description cannot be blank.",
            field="description",
        )
    if len(parsed_description) > 500:
        raise LedgerValidationError(
            code="INVALID_DESCRIPTION",
            message="Description cannot exceed 500 characters.",
            field="description",
        )
    if transaction_date.tzinfo is None or transaction_date.utcoffset() is None:
        raise LedgerValidationError(
            code="INVALID_TRANSACTION_DATE",
            message="Transaction date must include a timezone offset.",
            field="transactionDate",
        )

    return CreateTransactionCommand(
        amount=parsed_amount,
        currency=parsed_currency,
        transaction_type=transaction_type,
        description=parsed_description,
        transaction_date=transaction_date.astimezone(UTC),
        status=status,
        category_id=category_id,
    )


def parse_currency(currency: str) -> str:
    """Normalize a user-selected supported currency."""
    return _parse_currency(currency)


def _parse_amount(raw_amount: str) -> Decimal:
    if not isinstance(raw_amount, str) or not raw_amount:
        raise LedgerValidationError(
            code="INVALID_AMOUNT",
            message="Amount must be a positive decimal string.",
            field="amount",
        )
    if raw_amount != raw_amount.strip() or raw_amount.startswith(("+", "-")):
        raise LedgerValidationError(
            code="INVALID_AMOUNT",
            message="Amount must be a positive decimal string.",
            field="amount",
        )
    try:
        parsed = Decimal(raw_amount)
        return validate_positive_money(parsed)
    except (InvalidOperation, ValueError):
        raise LedgerValidationError(
            code="INVALID_AMOUNT",
            message="Amount must be positive, finite, and have at most four decimal places.",
            field="amount",
        ) from None


def _parse_currency(raw_currency: str) -> str:
    try:
        currency = normalize_currency_code(raw_currency)
    except ValueError:
        raise LedgerValidationError(
            code="INVALID_CURRENCY",
            message="Currency must be a supported three-letter code.",
            field="currency",
        ) from None
    if currency not in SUPPORTED_CURRENCIES:
        raise LedgerValidationError(
            code="UNSUPPORTED_CURRENCY",
            message="That currency is not supported in this phase.",
            field="currency",
        )
    return currency
