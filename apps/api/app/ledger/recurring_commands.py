"""Validated commands for deterministic recurring-payment workflows."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.domain.enums import RecurrenceRule, RecurringPaymentStatus
from app.domain.money import validate_positive_money
from app.domain.normalization import normalize_display_text, normalize_lookup_text
from app.ledger.commands import parse_currency
from app.ledger.errors import LedgerValidationError

_MUTABLE_STATUSES = frozenset(
    {
        RecurringPaymentStatus.ACTIVE,
        RecurringPaymentStatus.PAUSED,
        RecurringPaymentStatus.ENDED,
    }
)


@dataclass(frozen=True, slots=True)
class CreateRecurringPaymentCommand:
    """Normalized values for one manually managed recurring payment."""

    amount: Decimal
    currency: str
    merchant_name: str
    normalized_merchant_name: str
    recurrence_rule: RecurrenceRule
    next_expected_date: date


@dataclass(frozen=True, slots=True)
class TransitionRecurringPaymentCommand:
    """Requested lifecycle transition for one owner-scoped payment."""

    recurring_payment_id: UUID
    target_status: RecurringPaymentStatus


@dataclass(frozen=True, slots=True)
class RecordRecurringPaymentCommand:
    """Expected occurrence to turn into one posted manual expense."""

    recurring_payment_id: UUID
    expected_date: date
    transaction_date: datetime


@dataclass(frozen=True, slots=True)
class UpcomingRecurringWindow:
    """Inclusive user-supplied date window for upcoming totals."""

    start_date: date
    end_date: date


def parse_create_recurring_payment(
    *,
    amount: str,
    currency: str,
    merchant_name: str,
    recurrence_rule: RecurrenceRule,
    next_expected_date: date,
) -> CreateRecurringPaymentCommand:
    """Validate and normalize a manual recurring-payment command."""
    display_name = normalize_display_text(merchant_name)
    normalized_name = normalize_lookup_text(display_name)
    if not display_name or not normalized_name:
        raise LedgerValidationError(
            code="INVALID_MERCHANT",
            message="Merchant name cannot be blank.",
            field="merchantName",
        )
    if len(display_name) > 160 or len(normalized_name) > 160:
        raise LedgerValidationError(
            code="INVALID_MERCHANT",
            message="Merchant name cannot exceed 160 characters.",
            field="merchantName",
        )

    return CreateRecurringPaymentCommand(
        amount=_parse_amount(amount),
        currency=parse_currency(currency),
        merchant_name=display_name,
        normalized_merchant_name=normalized_name,
        recurrence_rule=recurrence_rule,
        next_expected_date=next_expected_date,
    )


def parse_recurring_status_transition(
    *,
    recurring_payment_id: UUID,
    target_status: RecurringPaymentStatus,
) -> TransitionRecurringPaymentCommand:
    """Reject statuses reserved for later automated review workflows."""
    if target_status not in _MUTABLE_STATUSES:
        raise LedgerValidationError(
            code="INVALID_RECURRING_STATUS",
            message="That recurring-payment status cannot be selected manually.",
            field="status",
        )
    return TransitionRecurringPaymentCommand(
        recurring_payment_id=recurring_payment_id,
        target_status=target_status,
    )


def parse_record_recurring_payment(
    *,
    recurring_payment_id: UUID,
    expected_date: date,
    transaction_date: datetime,
) -> RecordRecurringPaymentCommand:
    """Validate an occurrence timestamp before any financial write."""
    if transaction_date.tzinfo is None or transaction_date.utcoffset() is None:
        raise LedgerValidationError(
            code="INVALID_TRANSACTION_DATE",
            message="Transaction date must include a timezone offset.",
            field="transactionDate",
        )
    return RecordRecurringPaymentCommand(
        recurring_payment_id=recurring_payment_id,
        expected_date=expected_date,
        transaction_date=transaction_date.astimezone(UTC),
    )


def parse_upcoming_recurring_window(
    *,
    start_date: date,
    end_date: date,
) -> UpcomingRecurringWindow:
    """Validate an inclusive upcoming-payment date window."""
    if end_date < start_date:
        raise LedgerValidationError(
            code="INVALID_DATE_WINDOW",
            message="Window end date cannot be before its start date.",
            field="endDate",
        )
    return UpcomingRecurringWindow(start_date=start_date, end_date=end_date)


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
