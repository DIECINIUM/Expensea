"""Pure explainable duplicate scoring without model calls."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

from app.domain.enums import (
    NormalizedEventKind,
    ReconciliationDecision,
    TransactionType,
)
from app.domain.normalization import normalize_display_text
from app.models import NormalizedFinancialEvent
from app.reconciliation.dto import CandidateTransaction, ReconciliationResult
from app.reconciliation.policy import ReconciliationPolicy

SCORE_VERSION = "reconciliation-score/v1"
_SCORE_QUANTUM = Decimal("0.0001")
_EVENT_TYPES: dict[NormalizedEventKind, TransactionType] = {
    NormalizedEventKind.EXPENSE: TransactionType.EXPENSE,
    NormalizedEventKind.INCOME: TransactionType.INCOME,
    NormalizedEventKind.TRANSFER: TransactionType.TRANSFER,
    NormalizedEventKind.REFUND: TransactionType.REFUND,
    NormalizedEventKind.SHARED_EXPENSE: TransactionType.SHARED_EXPENSE,
}


def reconcile_candidates(
    event: NormalizedFinancialEvent,
    candidates: tuple[CandidateTransaction, ...],
    policy: ReconciliationPolicy,
) -> ReconciliationResult:
    """Select one stable best candidate, or return an explained new decision."""
    if not candidates:
        return ReconciliationResult(
            candidate_transaction_id=None,
            score=Decimal("0.0000"),
            decision=ReconciliationDecision.NEW_TRANSACTION,
            reasons=("NO_CANDIDATES", "SCORE_NEW_TRANSACTION"),
        )

    ranked = sorted(
        (score_candidate(event, candidate, policy) for candidate in candidates),
        key=lambda item: (
            -item.score,
            str(item.candidate_transaction_id),
        ),
    )
    return ranked[0]


def score_candidate(
    event: NormalizedFinancialEvent,
    candidate: CandidateTransaction,
    policy: ReconciliationPolicy,
) -> ReconciliationResult:
    """Score exact money, time, merchant, description, and typed identifiers."""
    if (
        event.amount is None
        or event.currency is None
        or event.occurred_at is None
        or event.amount != candidate.amount
        or event.currency != candidate.currency
        or _EVENT_TYPES.get(event.event_kind) is not candidate.transaction_type
    ):
        return ReconciliationResult(
            candidate_transaction_id=candidate.id,
            score=Decimal("0.0000"),
            decision=ReconciliationDecision.NEW_TRANSACTION,
            reasons=("MONEY_OR_TYPE_MISMATCH", "SCORE_NEW_TRANSACTION"),
        )

    event_identifiers = {item for item in event.payment_identifiers if isinstance(item, str)}
    candidate_identifiers = set(candidate.payment_identifiers)
    if event_identifiers.intersection(candidate_identifiers):
        return ReconciliationResult(
            candidate_transaction_id=candidate.id,
            score=Decimal("1.0000"),
            decision=ReconciliationDecision.MERGE,
            reasons=(
                "PAYMENT_IDENTIFIER_EXACT",
                "AMOUNT_CURRENCY_EXACT",
                "SCORE_AUTO_MERGE",
            ),
        )

    window_seconds = Decimal(str(policy.candidate_window.total_seconds()))
    delta_seconds = Decimal(
        str(abs((event.occurred_at - candidate.transaction_date).total_seconds()))
    )
    time_similarity = max(
        Decimal("0"),
        Decimal("1") - (delta_seconds / window_seconds),
    )
    merchant_similarity = _text_similarity(
        event.merchant_name,
        candidate.merchant_name,
    )
    description_similarity = _text_similarity(
        event.description,
        candidate.description,
    )
    score = (
        policy.amount_weight
        + policy.time_weight * time_similarity
        + policy.merchant_weight * merchant_similarity
        + policy.description_weight * description_similarity
    ).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)

    reasons = ["AMOUNT_CURRENCY_EXACT"]
    reasons.append("TIME_CLOSE" if time_similarity >= Decimal("0.95") else "TIME_WITHIN_WINDOW")
    if merchant_similarity == Decimal("1"):
        reasons.append("MERCHANT_EXACT")
    elif merchant_similarity >= Decimal("0.70"):
        reasons.append("MERCHANT_SIMILAR")
    if description_similarity == Decimal("1"):
        reasons.append("DESCRIPTION_EXACT")
    elif description_similarity >= Decimal("0.70"):
        reasons.append("DESCRIPTION_SIMILAR")

    if score >= policy.auto_merge_threshold:
        decision = ReconciliationDecision.MERGE
        reasons.append("SCORE_AUTO_MERGE")
    elif score >= policy.possible_duplicate_threshold:
        decision = ReconciliationDecision.POSSIBLE_DUPLICATE
        reasons.append("SCORE_POSSIBLE_DUPLICATE")
    else:
        decision = ReconciliationDecision.NEW_TRANSACTION
        reasons.append("SCORE_NEW_TRANSACTION")
    return ReconciliationResult(
        candidate_transaction_id=candidate.id,
        score=score,
        decision=decision,
        reasons=tuple(reasons),
    )


def _text_similarity(left: str | None, right: str | None) -> Decimal:
    if left is None or right is None:
        return Decimal("0")
    normalized_left = normalize_display_text(left).casefold()
    normalized_right = normalize_display_text(right).casefold()
    if not normalized_left or not normalized_right:
        return Decimal("0")
    if normalized_left == normalized_right:
        return Decimal("1")
    character_ratio = Decimal(str(SequenceMatcher(None, normalized_left, normalized_right).ratio()))
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    token_union = left_tokens | right_tokens
    token_ratio = (
        Decimal(len(left_tokens & right_tokens)) / Decimal(len(token_union))
        if token_union
        else Decimal("0")
    )
    return max(character_ratio, token_ratio).quantize(
        _SCORE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
