from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.enums import CategorizationSource


@dataclass(frozen=True, slots=True)
class CategoryAssignment:
    category_id: UUID
    source: CategorizationSource
    version: str
    confidence: Decimal
    overridden: bool = False


@dataclass(frozen=True, slots=True)
class CorrectionView:
    id: UUID
    transaction_id: UUID
    previous_category_name: str | None
    corrected_category_name: str
    classifier_version: str
    confidence: Decimal
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CategoryRuleView:
    id: UUID
    pattern: str
    category_id: UUID
    category_name: str
    priority: int
    enabled: bool
