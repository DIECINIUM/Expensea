"""Pure non-vector categorization policy."""

from decimal import Decimal
from uuid import UUID

from app.categorization.dto import CategoryAssignment
from app.domain.enums import CategorizationSource

CLASSIFIER_VERSION = "categorization-v1"
RETRIEVAL_THRESHOLD = Decimal("0.6000")


def normalized_words(value: str) -> frozenset[str]:
    return frozenset(word for word in value.casefold().split() if len(word) > 1)


def jaccard(left: str, right: str) -> Decimal:
    left_words = normalized_words(left)
    right_words = normalized_words(right)
    union = left_words | right_words
    if not union:
        return Decimal("0.0000")
    return (Decimal(len(left_words & right_words)) / Decimal(len(union))).quantize(
        Decimal("0.0001")
    )


def retrieval_assignment(
    description: str,
    candidates: tuple[tuple[str, UUID], ...],
) -> CategoryAssignment | None:
    scored = [
        (jaccard(description, candidate), category_id) for candidate, category_id in candidates
    ]
    eligible = [
        (score, category_id) for score, category_id in scored if score >= RETRIEVAL_THRESHOLD
    ]
    if not eligible:
        return None
    best_score = max(score for score, _ in eligible)
    best_categories = {category_id for score, category_id in eligible if score == best_score}
    if len(best_categories) != 1:
        return None
    return CategoryAssignment(
        category_id=best_categories.pop(),
        source=CategorizationSource.RETRIEVAL,
        version=CLASSIFIER_VERSION,
        confidence=best_score,
    )
