from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.domain.enums import TransactionType


@dataclass(frozen=True, slots=True)
class AnalyticsTransaction:
    id: UUID
    amount: Decimal
    transaction_type: TransactionType
    occurred_at: datetime
    merchant_id: UUID | None
    merchant_name: str | None
    category_id: UUID | None
    category_name: str


@dataclass(frozen=True, slots=True)
class OverdueReceivable:
    id: UUID
    due_date: date


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    spent: Decimal
    transaction_count: int
    average_size: Decimal


@dataclass(frozen=True, slots=True)
class CategoryContribution:
    category_id: UUID | None
    category_name: str
    current_amount: Decimal
    previous_amount: Decimal
    change: Decimal


@dataclass(frozen=True, slots=True)
class GroundedInsight:
    code: str
    title: str
    detail: str
    amount: Decimal | None
    percentage: int | None
    supporting_transaction_ids: tuple[UUID, ...]
    supporting_obligation_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class AnalyticsReport:
    currency: str
    current_period_start: date
    current_period_end: date
    previous_period_start: date
    previous_period_end: date
    current: PeriodMetrics
    previous: PeriodMetrics
    total_change: Decimal
    count_change: int
    average_size_change: Decimal
    contributions: tuple[CategoryContribution, ...]
    insights: tuple[GroundedInsight, ...]
