"""Pure deterministic reconciliation scoring tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.enums import (
    NormalizedEventKind,
    ReconciliationDecision,
    TransactionType,
)
from app.models import NormalizedFinancialEvent
from app.reconciliation.dto import CandidateTransaction
from app.reconciliation.policy import ReconciliationPolicy
from app.reconciliation.scoring import reconcile_candidates, score_candidate

EVENT_ID = UUID("d1000000-0000-4000-8000-000000000001")
RAW_ID = UUID("d2000000-0000-4000-8000-000000000001")
CANDIDATE_ID = UUID("d3000000-0000-4000-8000-000000000001")
OCCURRED_AT = datetime(2026, 7, 24, 15, 1, tzinfo=UTC)


def _event(
    *,
    payment_identifiers: list[str] | None = None,
) -> NormalizedFinancialEvent:
    return NormalizedFinancialEvent(
        id=EVENT_ID,
        user_id=UUID("d4000000-0000-4000-8000-000000000001"),
        raw_event_id=RAW_ID,
        schema_version="financial-event/v1",
        normalizer_key="fixture",
        normalizer_version="1",
        event_kind=NormalizedEventKind.EXPENSE,
        amount=Decimal("480.0000"),
        currency="INR",
        description="Swiggy dinner order",
        occurred_at=OCCURRED_AT,
        merchant_name="Swiggy",
        category_hint="Food Delivery",
        tags=[],
        payment_identifiers=payment_identifiers or [],
        confidence=Decimal("1.0000"),
    )


def _candidate(
    *,
    candidate_id: UUID = CANDIDATE_ID,
    description: str = "Swiggy dinner order",
    merchant_name: str | None = "Swiggy",
    transaction_date: datetime = OCCURRED_AT + timedelta(minutes=1),
    payment_identifiers: tuple[str, ...] = (),
    amount: Decimal = Decimal("480.0000"),
    transaction_type: TransactionType = TransactionType.EXPENSE,
) -> CandidateTransaction:
    return CandidateTransaction(
        id=candidate_id,
        amount=amount,
        currency="INR",
        transaction_type=transaction_type,
        description=description,
        transaction_date=transaction_date,
        merchant_name=merchant_name,
        payment_identifiers=payment_identifiers,
    )


def test_matching_money_time_merchant_and_description_auto_merge() -> None:
    result = score_candidate(_event(), _candidate(), ReconciliationPolicy())

    assert result.decision is ReconciliationDecision.MERGE
    assert result.score >= Decimal("0.99")
    assert result.reasons == (
        "AMOUNT_CURRENCY_EXACT",
        "TIME_CLOSE",
        "MERCHANT_EXACT",
        "DESCRIPTION_EXACT",
        "SCORE_AUTO_MERGE",
    )


def test_weaker_merchant_match_routes_to_review_instead_of_silent_merge() -> None:
    result = score_candidate(
        _event(),
        _candidate(description="Card purchase", merchant_name="Swiggy"),
        ReconciliationPolicy(),
    )

    assert result.decision is ReconciliationDecision.POSSIBLE_DUPLICATE
    assert Decimal("0.70") <= result.score < Decimal("0.92")
    assert result.reasons[-1] == "SCORE_POSSIBLE_DUPLICATE"


def test_money_and_time_alone_create_a_new_transaction() -> None:
    result = score_candidate(
        _event(),
        _candidate(description="Unrelated", merchant_name=None),
        ReconciliationPolicy(),
    )

    assert result.decision is ReconciliationDecision.NEW_TRANSACTION
    assert result.score < Decimal("0.70")


def test_exact_typed_identifier_requires_matching_money_and_type() -> None:
    event = _event(payment_identifiers=["upi:123456789012"])
    exact = score_candidate(
        event,
        _candidate(
            description="Different source wording",
            merchant_name=None,
            transaction_date=OCCURRED_AT + timedelta(days=5),
            payment_identifiers=("upi:123456789012",),
        ),
        ReconciliationPolicy(),
    )
    wrong_type = score_candidate(
        event,
        _candidate(
            payment_identifiers=("upi:123456789012",),
            transaction_type=TransactionType.INCOME,
        ),
        ReconciliationPolicy(),
    )

    assert exact.decision is ReconciliationDecision.MERGE
    assert exact.score == Decimal("1.0000")
    assert exact.reasons[0] == "PAYMENT_IDENTIFIER_EXACT"
    assert wrong_type.decision is ReconciliationDecision.NEW_TRANSACTION
    assert wrong_type.score == Decimal("0.0000")


def test_candidate_selection_is_stable_and_explains_an_empty_set() -> None:
    better_id = UUID("d3000000-0000-4000-8000-000000000002")
    candidates = (
        _candidate(description="Unrelated"),
        _candidate(candidate_id=better_id),
    )

    selected = reconcile_candidates(_event(), candidates, ReconciliationPolicy())
    empty = reconcile_candidates(_event(), (), ReconciliationPolicy())

    assert selected.candidate_transaction_id == better_id
    assert empty.decision is ReconciliationDecision.NEW_TRANSACTION
    assert empty.reasons == ("NO_CANDIDATES", "SCORE_NEW_TRANSACTION")


@pytest.mark.parametrize(
    "policy",
    [
        {
            "possible_duplicate_threshold": Decimal("0.95"),
            "auto_merge_threshold": Decimal("0.90"),
        },
        {"amount_weight": Decimal("0.50")},
        {"candidate_window_minutes": 0},
        {"max_candidates": 101},
    ],
)
def test_policy_rejects_unsafe_thresholds_and_bounds(
    policy: dict[str, Decimal | int],
) -> None:
    with pytest.raises(ValueError):
        ReconciliationPolicy(**policy)
