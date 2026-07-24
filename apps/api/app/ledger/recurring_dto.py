"""Owner-scoped values returned by recurring-payment workflows."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.domain.enums import RecurrenceRule, RecurringPaymentStatus


@dataclass(frozen=True, slots=True)
class RecurringPaymentView:
    """One recurring payment visible inside its owner's ledger."""

    id: UUID
    merchant_id: UUID
    merchant_name: str
    amount: Decimal
    currency: str
    recurrence_rule: RecurrenceRule
    next_expected_date: date
    status: RecurringPaymentStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UpcomingRecurringTotal:
    """Exact active recurring total for one currency and date window."""

    currency: str
    amount: Decimal
    payment_count: int
    window_start: date
    window_end: date


@dataclass(frozen=True, slots=True)
class RecordedRecurringPaymentView:
    """The expense created for one expected occurrence and its advanced schedule."""

    recorded_expected_date: date
    transaction_id: UUID
    transaction_date: datetime
    payment: RecurringPaymentView
