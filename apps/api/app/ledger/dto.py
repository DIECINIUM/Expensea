"""Immutable values returned by deterministic ledger services."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.domain.enums import TransactionStatus, TransactionType


@dataclass(frozen=True, slots=True)
class UserView:
    """The authenticated ledger owner's public profile."""

    id: UUID
    name: str
    default_currency: str
    timezone: str


@dataclass(frozen=True, slots=True)
class CategoryView:
    """A system or owner-local category available for manual entry."""

    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class MerchantSpending:
    """Signed spending contribution for one merchant."""

    merchant_id: UUID | None
    merchant_name: str
    amount: Decimal
    currency: str
    share_percentage: int


@dataclass(frozen=True, slots=True)
class TransactionView:
    """A tenant-safe transaction projection."""

    id: UUID
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    description: str
    transaction_date: datetime
    status: TransactionStatus
    merchant_name: str | None
    category_name: str | None


@dataclass(frozen=True, slots=True)
class TransactionEdge:
    """One transaction and the opaque cursor for its stable position."""

    cursor: str
    node: TransactionView


@dataclass(frozen=True, slots=True)
class TransactionPage:
    """Forward-only keyset page."""

    edges: tuple[TransactionEdge, ...]
    has_next_page: bool
    end_cursor: str | None


@dataclass(frozen=True, slots=True)
class FinancialSummary:
    """Exact totals for one currency and user-local calendar month."""

    currency: str
    period_start: date
    period_end: date
    spent: Decimal
    income: Decimal
    transaction_count: int


@dataclass(frozen=True, slots=True)
class CategorySpending:
    """Signed spending contribution for one category."""

    category_id: UUID | None
    category_name: str
    amount: Decimal
    currency: str
    share_percentage: int


@dataclass(frozen=True, slots=True)
class MonthlySpending:
    """Signed spending total for one user-local calendar month."""

    month_start: date
    amount: Decimal
    currency: str
