"""Immutable projections for the financial-event review queue."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.enums import (
    ConnectorType,
    NormalizedEventKind,
    ProposalStatus,
    RecurrenceRule,
)


@dataclass(frozen=True, slots=True)
class RawExtractionContext:
    """Owner-authorized raw text and trusted user defaults for extraction."""

    raw_event_id: UUID
    connector_type: ConnectorType
    occurred_at: datetime | None
    payload: dict[str, Any]
    timezone: str
    default_currency: str


@dataclass(frozen=True, slots=True)
class FinancialEventProposalView:
    """User-visible proposal without raw private payload or model reasoning."""

    id: UUID
    raw_event_id: UUID
    source: ConnectorType
    event_kind: NormalizedEventKind
    amount: Decimal | None
    currency: str | None
    description: str
    occurred_at: datetime | None
    due_date: date | None
    merchant_name: str | None
    counterparty: str | None
    recurrence_rule: RecurrenceRule | None
    next_expected_date: date | None
    category_hint: str | None
    tags: tuple[str, ...]
    confidence: Decimal
    status: ProposalStatus
    review_reasons: tuple[str, ...]
    provider: str
    model: str
    prompt_version: str
    created_at: datetime
    canonical_target_type: str | None
    canonical_target_id: UUID | None
