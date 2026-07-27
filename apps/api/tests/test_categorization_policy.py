"""Deterministic non-vector retrieval behavior."""

from uuid import UUID

from app.categorization.policy import jaccard, retrieval_assignment
from app.domain.enums import CategorizationSource

FOOD_ID = UUID("70000000-0000-4000-8000-000000000001")
TRAVEL_ID = UUID("70000000-0000-4000-8000-000000000002")


def test_retrieval_uses_unique_best_verified_correction() -> None:
    result = retrieval_assignment(
        "airport taxi ride",
        (
            ("airport taxi", TRAVEL_ID),
            ("restaurant dinner", FOOD_ID),
        ),
    )

    assert result is not None
    assert result.category_id == TRAVEL_ID
    assert result.source is CategorizationSource.RETRIEVAL
    assert str(result.confidence) == "0.6667"


def test_retrieval_rejects_tied_categories_and_weak_matches() -> None:
    assert (
        retrieval_assignment(
            "coffee shop",
            (("coffee shop", FOOD_ID), ("coffee shop", TRAVEL_ID)),
        )
        is None
    )
    assert retrieval_assignment("monthly rent", (("airport taxi", TRAVEL_ID),)) is None
    assert str(jaccard("", "")) == "0.0000"
