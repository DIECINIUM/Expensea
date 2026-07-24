"""Validated configurable reconciliation policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationPolicy:
    """Candidate bounds, scoring weights, and conservative decision thresholds."""

    candidate_window_minutes: int = 1_440
    max_candidates: int = 20
    possible_duplicate_threshold: Decimal = Decimal("0.70")
    auto_merge_threshold: Decimal = Decimal("0.92")
    amount_weight: Decimal = Decimal("0.35")
    time_weight: Decimal = Decimal("0.25")
    merchant_weight: Decimal = Decimal("0.20")
    description_weight: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        if self.candidate_window_minutes < 1 or self.candidate_window_minutes > 10_080:
            raise ValueError("candidate_window_minutes must be between 1 and 10080")
        if self.max_candidates < 1 or self.max_candidates > 100:
            raise ValueError("max_candidates must be between 1 and 100")
        values = (
            self.possible_duplicate_threshold,
            self.auto_merge_threshold,
            self.amount_weight,
            self.time_weight,
            self.merchant_weight,
            self.description_weight,
        )
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("reconciliation thresholds and weights must be between 0 and 1")
        if self.possible_duplicate_threshold >= self.auto_merge_threshold:
            raise ValueError("possible duplicate threshold must be lower than auto merge")
        if self.weight_total != Decimal("1"):
            raise ValueError("reconciliation weights must sum to exactly 1")

    @property
    def candidate_window(self) -> timedelta:
        return timedelta(minutes=self.candidate_window_minutes)

    @property
    def weight_total(self) -> Decimal:
        return (
            self.amount_weight + self.time_weight + self.merchant_weight + self.description_weight
        )
