"""Immutable reconciliation inputs, outcomes, and public projections."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.enums import (
    ConnectorType,
    NormalizedEventKind,
    ReconciliationActionType,
    ReconciliationDecision,
    ReconciliationStatus,
    TransactionType,
)


@dataclass(frozen=True, slots=True)
class CandidateTransaction:
    """Owner-scoped canonical transaction considered by the scoring engine."""

    id: UUID
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    description: str
    transaction_date: datetime
    merchant_name: str | None
    payment_identifiers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Explainable best-candidate decision required by the Phase 4 contract."""

    candidate_transaction_id: UUID | None
    score: Decimal
    decision: ReconciliationDecision
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationProcessingOutcome:
    """Canonical handoff result for ingestion or proposal approval."""

    case_id: UUID
    transaction_id: UUID | None
    result: ReconciliationResult

    @property
    def requires_review(self) -> bool:
        return self.result.decision is ReconciliationDecision.POSSIBLE_DUPLICATE


@dataclass(frozen=True, slots=True)
class ReconciliationActionView:
    """Content-free append-only decision history."""

    id: UUID
    action_type: ReconciliationActionType
    from_transaction_id: UUID | None
    to_transaction_id: UUID | None
    score: Decimal
    reasons: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReconciliationCaseView:
    """Owner-visible case without raw source payloads."""

    id: UUID
    normalized_event_id: UUID
    source: ConnectorType
    event_kind: NormalizedEventKind
    amount: Decimal
    currency: str
    description: str
    occurred_at: datetime
    merchant_name: str | None
    candidate_transaction_id: UUID | None
    candidate_description: str | None
    candidate_occurred_at: datetime | None
    candidate_merchant_name: str | None
    resulting_transaction_id: UUID | None
    initial_decision: ReconciliationDecision
    status: ReconciliationStatus
    score: Decimal
    score_version: str
    reasons: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    actions: tuple[ReconciliationActionView, ...]

    @property
    def can_unmerge(self) -> bool:
        return self.status is ReconciliationStatus.MERGED
