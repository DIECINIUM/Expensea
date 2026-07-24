"""Validated commands accepted by the ledger application service."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.domain.enums import TransactionSource, TransactionStatus, TransactionType
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
    """Normalized values for one deterministic ledger transaction."""

    amount: Decimal
    currency: str
    transaction_type: TransactionType
    description: str
    transaction_date: datetime
    status: TransactionStatus
    category_id: UUID | None
    merchant_name: str | None
    merchant_normalized_name: str | None
    source: TransactionSource
    confidence: Decimal | None


@dataclass(frozen=True, slots=True)
class CreateCategoryCommand:
    """Normalized values for one owner-local category."""

    name: str
    normalized_name: str
    parent_category_id: UUID | None


def parse_create_transaction(
    *,
    amount: str,
    currency: str,
    transaction_type: TransactionType,
    description: str,
    transaction_date: datetime,
    status: TransactionStatus = TransactionStatus.POSTED,
    category_id: UUID | None = None,
    merchant_name: str | None = None,
    source: TransactionSource = TransactionSource.MANUAL,
    confidence: Decimal | None = None,
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
    parsed_merchant_name, parsed_merchant_lookup = _parse_optional_merchant_name(merchant_name)
    parsed_confidence = _parse_optional_confidence(confidence)

    return CreateTransactionCommand(
        amount=parsed_amount,
        currency=parsed_currency,
        transaction_type=transaction_type,
        description=parsed_description,
        transaction_date=transaction_date.astimezone(UTC),
        status=status,
        category_id=category_id,
        merchant_name=parsed_merchant_name,
        merchant_normalized_name=parsed_merchant_lookup,
        source=source,
        confidence=parsed_confidence,
    )


def parse_create_category(
    *,
    name: str,
    parent_category_id: UUID | None = None,
) -> CreateCategoryCommand:
    """Validate and normalize a private category command."""
    parsed_name = normalize_display_text(name)
    if not parsed_name:
        raise LedgerValidationError(
            code="INVALID_CATEGORY_NAME",
            message="Category name cannot be blank.",
            field="name",
        )
    if len(parsed_name) > 80:
        raise LedgerValidationError(
            code="INVALID_CATEGORY_NAME",
            message="Category name cannot exceed 80 characters.",
            field="name",
        )
    return CreateCategoryCommand(
        name=parsed_name,
        normalized_name=parsed_name.casefold(),
        parent_category_id=parent_category_id,
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


def _parse_optional_merchant_name(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    display_name = normalize_display_text(value)
    if not display_name:
        return None, None
    if len(display_name) > 160:
        raise LedgerValidationError(
            code="INVALID_MERCHANT_NAME",
            message="Merchant name cannot exceed 160 characters.",
            field="merchantName",
        )
    return display_name, display_name.casefold()


def _parse_optional_confidence(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if not value.is_finite() or value < 0 or value > 1:
        raise LedgerValidationError(
            code="INVALID_CONFIDENCE",
            message="Confidence must be between zero and one.",
            field="confidence",
        )
    return value.quantize(Decimal("0.0001"))
