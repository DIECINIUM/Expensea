"""Persisted Phase 1 ledger vocabularies."""

from enum import StrEnum


def enum_values[EnumType: StrEnum](enum_type: type[EnumType]) -> list[str]:
    """Persist stable enum values rather than Python member names."""
    return [member.value for member in enum_type]


class TransactionType(StrEnum):
    """Economic direction of a ledger transaction."""

    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    REFUND = "refund"
    SHARED_EXPENSE = "shared_expense"


class TransactionStatus(StrEnum):
    """Posting lifecycle for a ledger transaction."""

    PENDING = "pending"
    POSTED = "posted"
    VOIDED = "voided"


class TransactionSource(StrEnum):
    """Normalized origin of a transaction in the current phase."""

    MANUAL = "manual"


class ObligationStatus(StrEnum):
    """Settlement lifecycle for receivables and payables."""

    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class RecurrenceRule(StrEnum):
    """Manually managed recurrence rules supported in Phase 1."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RecurringPaymentStatus(StrEnum):
    """Lifecycle for an expected recurring payment."""

    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    NEEDS_REVIEW = "needs_review"
