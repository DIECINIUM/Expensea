"""Labelled synthetic evaluation for deterministic duplicate reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Self
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.domain.enums import (
    NormalizedEventKind,
    ReconciliationDecision,
    TransactionSource,
    TransactionType,
)
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ledger.commands import parse_create_transaction
from app.ledger.errors import LedgerValidationError
from app.models import NormalizedFinancialEvent
from app.reconciliation.dto import CandidateTransaction
from app.reconciliation.policy import ReconciliationPolicy
from app.reconciliation.scoring import SCORE_VERSION, reconcile_candidates

DATASET_VERSION = "reconciliation/v1"
_EVENT_TYPES: dict[NormalizedEventKind, TransactionType] = {
    NormalizedEventKind.EXPENSE: TransactionType.EXPENSE,
    NormalizedEventKind.INCOME: TransactionType.INCOME,
    NormalizedEventKind.TRANSFER: TransactionType.TRANSFER,
    NormalizedEventKind.REFUND: TransactionType.REFUND,
    NormalizedEventKind.SHARED_EXPENSE: TransactionType.SHARED_EXPENSE,
}


class CandidateEvaluationInput(BaseModel):
    """Strict synthetic representation of one existing canonical transaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    currency: str
    transaction_type: TransactionType
    description: str = Field(min_length=1, max_length=500)
    transaction_date: datetime
    merchant_name: str | None = Field(default=None, max_length=160)
    payment_identifiers: tuple[str, ...] = ()

    @field_validator("transaction_date")
    @classmethod
    def require_aware_transaction_date(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("candidate transaction_date must include a timezone offset")
        return value.astimezone(UTC)

    @field_validator("payment_identifiers", mode="before")
    @classmethod
    def normalize_payment_identifiers(cls, value: object) -> object:
        validated = NormalizedFinancialEventV1(
            event_kind=NormalizedEventKind.UNKNOWN,
            description="Identifier validation fixture",
            payment_identifiers=value,
        )
        return validated.payment_identifiers

    @model_validator(mode="after")
    def validate_transaction_fields(self) -> Self:
        try:
            parse_create_transaction(
                amount=format(self.amount, "f"),
                currency=self.currency,
                transaction_type=self.transaction_type,
                description=self.description,
                transaction_date=self.transaction_date,
                merchant_name=self.merchant_name,
                source=TransactionSource.INGESTION,
            )
        except LedgerValidationError as exc:
            raise ValueError("candidate transaction fields are invalid") from exc
        return self


class ReconciliationEvaluationCase(BaseModel):
    """One synthetic source/candidate pair with a human-reviewed label."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    event: NormalizedFinancialEventV1
    candidate: CandidateEvaluationInput
    is_duplicate: bool
    expected_decision: ReconciliationDecision
    slices: tuple[str, ...] = Field(min_length=1, max_length=12)

    @field_validator("slices")
    @classmethod
    def normalize_slices(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip().casefold() for item in value if item.strip()))
        if not normalized:
            raise ValueError("at least one non-blank reconciliation slice is required")
        return normalized

    @model_validator(mode="after")
    def require_postable_event(self) -> Self:
        if (
            self.event.event_kind not in _EVENT_TYPES
            or self.event.amount is None
            or self.event.currency is None
            or self.event.occurred_at is None
        ):
            raise ValueError("reconciliation evaluation events must be postable transactions")
        if not self.is_duplicate and self.expected_decision is ReconciliationDecision.MERGE:
            raise ValueError("a labelled non-duplicate cannot expect an automatic merge")
        return self


@dataclass(frozen=True, slots=True)
class LoadedReconciliationDataset:
    """Validated cases plus the exact content hash used for one evaluation."""

    cases: tuple[ReconciliationEvaluationCase, ...]
    sha256: str


def load_reconciliation_dataset(path: Path) -> LoadedReconciliationDataset:
    """Load strict JSONL and reject duplicate labels."""
    content = path.read_bytes()
    cases: list[ReconciliationEvaluationCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            case = ReconciliationEvaluationCase.model_validate_json(raw_line)
        except ValidationError as exc:
            raise ValueError(f"invalid reconciliation dataset row {line_number}") from exc
        if case.id in seen_ids:
            raise ValueError(f"duplicate reconciliation dataset id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError("reconciliation evaluation dataset is empty")
    return LoadedReconciliationDataset(
        cases=tuple(cases),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def evaluate_reconciliation_dataset(
    dataset: LoadedReconciliationDataset,
    policy: ReconciliationPolicy | None = None,
) -> dict[str, Any]:
    """Run the pure scorer and report merge safety, review load, and misses."""
    selected_policy = policy or ReconciliationPolicy()
    case_reports: list[dict[str, Any]] = []
    slice_outcomes: dict[str, list[tuple[bool, ReconciliationDecision]]] = defaultdict(list)
    outcomes: list[tuple[bool, ReconciliationDecision]] = []
    expected_correct = 0

    for case in dataset.cases:
        event = _event_model(case)
        candidate = _candidate(case)
        result = reconcile_candidates(event, (candidate,), selected_policy)
        outcomes.append((case.is_duplicate, result.decision))
        for slice_name in case.slices:
            slice_outcomes[slice_name].append((case.is_duplicate, result.decision))
        decision_correct = result.decision is case.expected_decision
        expected_correct += int(decision_correct)
        case_reports.append(
            {
                "id": case.id,
                "is_duplicate": case.is_duplicate,
                "expected_decision": case.expected_decision.value,
                "actual_decision": result.decision.value,
                "decision_correct": decision_correct,
                "score": format(result.score, "f"),
                "reasons": list(result.reasons),
            }
        )

    metrics = _metrics(outcomes)
    metrics["expected_decision_accuracy"] = _ratio(expected_correct, len(outcomes))
    return {
        "dataset": {
            "version": DATASET_VERSION,
            "sha256": dataset.sha256,
            "case_count": len(dataset.cases),
        },
        "contract": {
            "score_version": SCORE_VERSION,
            "possible_duplicate_threshold": format(
                selected_policy.possible_duplicate_threshold,
                "f",
            ),
            "auto_merge_threshold": format(
                selected_policy.auto_merge_threshold,
                "f",
            ),
            "candidate_window_minutes": selected_policy.candidate_window_minutes,
            "weights": {
                "amount": format(selected_policy.amount_weight, "f"),
                "time": format(selected_policy.time_weight, "f"),
                "merchant": format(selected_policy.merchant_weight, "f"),
                "description": format(selected_policy.description_weight, "f"),
            },
        },
        "quality": metrics,
        "slices": {
            slice_name: _metrics(slice_values)
            for slice_name, slice_values in sorted(slice_outcomes.items())
        },
        "cases": case_reports,
    }


def reconciliation_report_json(report: dict[str, Any]) -> str:
    """Serialize a deterministic, source-content-free evaluation report."""
    return json.dumps(report, indent=2, sort_keys=True)


def _event_model(case: ReconciliationEvaluationCase) -> NormalizedFinancialEvent:
    event = case.event
    return NormalizedFinancialEvent(
        id=uuid5(NAMESPACE_URL, f"reconciliation-event:{case.id}"),
        user_id=uuid5(NAMESPACE_URL, "reconciliation-evaluation-user"),
        raw_event_id=uuid5(NAMESPACE_URL, f"reconciliation-raw:{case.id}"),
        schema_version=event.schema_version,
        normalizer_key="evaluation",
        normalizer_version="1",
        event_kind=event.event_kind,
        amount=event.amount,
        currency=event.currency,
        description=event.description,
        occurred_at=event.occurred_at,
        merchant_name=event.merchant_name,
        counterparty=event.counterparty,
        category_hint=event.category_hint,
        tags=list(event.tags),
        payment_identifiers=list(event.payment_identifiers),
        confidence=event.confidence,
    )


def _candidate(case: ReconciliationEvaluationCase) -> CandidateTransaction:
    candidate = case.candidate
    return CandidateTransaction(
        id=uuid5(NAMESPACE_URL, f"reconciliation-candidate:{case.id}"),
        amount=candidate.amount,
        currency=candidate.currency,
        transaction_type=candidate.transaction_type,
        description=candidate.description,
        transaction_date=candidate.transaction_date,
        merchant_name=candidate.merchant_name,
        payment_identifiers=candidate.payment_identifiers,
    )


def _metrics(
    outcomes: list[tuple[bool, ReconciliationDecision]],
) -> dict[str, int | float | list[str]]:
    true_merges = sum(
        is_duplicate and decision is ReconciliationDecision.MERGE
        for is_duplicate, decision in outcomes
    )
    false_merges = sum(
        not is_duplicate and decision is ReconciliationDecision.MERGE
        for is_duplicate, decision in outcomes
    )
    missed_auto_merges = sum(
        is_duplicate and decision is not ReconciliationDecision.MERGE
        for is_duplicate, decision in outcomes
    )
    reviews = sum(decision is ReconciliationDecision.POSSIBLE_DUPLICATE for _, decision in outcomes)
    false_new = sum(
        is_duplicate and decision is ReconciliationDecision.NEW_TRANSACTION
        for is_duplicate, decision in outcomes
    )
    merge_precision = _ratio(true_merges, true_merges + false_merges)
    merge_recall = _ratio(true_merges, true_merges + missed_auto_merges)
    return {
        "cases": len(outcomes),
        "labelled_duplicates": sum(is_duplicate for is_duplicate, _ in outcomes),
        "automatic_merges": true_merges + false_merges,
        "automatic_merge_precision": merge_precision,
        "automatic_merge_recall": merge_recall,
        "automatic_merge_f1": _f1(merge_precision, merge_recall),
        "possible_duplicate_reviews": reviews,
        "possible_duplicate_review_rate": _ratio(reviews, len(outcomes)),
        "false_merges": false_merges,
        "false_new_decisions": false_new,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
