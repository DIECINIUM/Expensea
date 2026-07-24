"""Validated commands for people, obligations, and settlement history."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.domain.money import validate_positive_money
from app.domain.normalization import normalize_display_text, normalize_lookup_text
from app.ledger.commands import parse_currency
from app.ledger.errors import LedgerValidationError


@dataclass(frozen=True, slots=True)
class CreatePersonCommand:
    """Normalized identity for one owner-local person."""

    name: str
    normalized_name: str


@dataclass(frozen=True, slots=True)
class CreateObligationCommand:
    """Validated principal and references for a receivable or payable."""

    person_id: UUID
    amount: Decimal
    currency: str
    description: str
    issued_date: date
    due_date: date | None
    transaction_id: UUID | None


@dataclass(frozen=True, slots=True)
class SettleObligationCommand:
    """Validated immutable payment against one obligation."""

    amount: Decimal
    currency: str
    settled_at: datetime
    transaction_id: UUID | None
    note: str | None


def parse_create_person(*, name: str) -> CreatePersonCommand:
    """Normalize a user-entered person name into display and lookup forms."""
    display_name = normalize_display_text(name)
    if not display_name:
        raise LedgerValidationError(
            code="INVALID_PERSON_NAME",
            message="Person name cannot be blank.",
            field="name",
        )
    if len(display_name) > 120:
        raise LedgerValidationError(
            code="INVALID_PERSON_NAME",
            message="Person name cannot exceed 120 characters.",
            field="name",
        )
    return CreatePersonCommand(
        name=display_name,
        normalized_name=normalize_lookup_text(display_name),
    )


def parse_create_obligation(
    *,
    person_id: UUID,
    amount: str,
    currency: str,
    description: str,
    issued_date: date,
    due_date: date | None = None,
    transaction_id: UUID | None = None,
) -> CreateObligationCommand:
    """Validate common receivable/payable creation input."""
    parsed_description = _parse_description(description)
    if due_date is not None and due_date < issued_date:
        raise LedgerValidationError(
            code="INVALID_DUE_DATE",
            message="Due date cannot be before the issued date.",
            field="dueDate",
        )
    return CreateObligationCommand(
        person_id=person_id,
        amount=_parse_amount(amount),
        currency=parse_currency(currency),
        description=parsed_description,
        issued_date=issued_date,
        due_date=due_date,
        transaction_id=transaction_id,
    )


def parse_settlement(
    *,
    amount: str,
    currency: str,
    settled_at: datetime,
    transaction_id: UUID | None = None,
    note: str | None = None,
) -> SettleObligationCommand:
    """Validate a partial or complete settlement command."""
    if settled_at.tzinfo is None or settled_at.utcoffset() is None:
        raise LedgerValidationError(
            code="INVALID_SETTLEMENT_DATE",
            message="Settlement date must include a timezone offset.",
            field="settledAt",
        )

    normalized_note = normalize_display_text(note) if note is not None else None
    if normalized_note == "":
        normalized_note = None
    if normalized_note is not None and len(normalized_note) > 500:
        raise LedgerValidationError(
            code="INVALID_SETTLEMENT_NOTE",
            message="Settlement note cannot exceed 500 characters.",
            field="note",
        )

    return SettleObligationCommand(
        amount=_parse_amount(amount),
        currency=parse_currency(currency),
        settled_at=settled_at.astimezone(UTC),
        transaction_id=transaction_id,
        note=normalized_note,
    )


def _parse_amount(raw_amount: str) -> Decimal:
    if not isinstance(raw_amount, str) or not raw_amount:
        raise _invalid_amount()
    if raw_amount != raw_amount.strip() or raw_amount.startswith(("+", "-")):
        raise _invalid_amount()
    try:
        return validate_positive_money(Decimal(raw_amount))
    except (InvalidOperation, ValueError):
        raise _invalid_amount() from None


def _invalid_amount() -> LedgerValidationError:
    return LedgerValidationError(
        code="INVALID_AMOUNT",
        message="Amount must be positive, finite, and have at most four decimal places.",
        field="amount",
    )


def _parse_description(description: str) -> str:
    normalized = normalize_display_text(description)
    if not normalized:
        raise LedgerValidationError(
            code="INVALID_DESCRIPTION",
            message="Description cannot be blank.",
            field="description",
        )
    if len(normalized) > 500:
        raise LedgerValidationError(
            code="INVALID_DESCRIPTION",
            message="Description cannot exceed 500 characters.",
            field="description",
        )
    return normalized
