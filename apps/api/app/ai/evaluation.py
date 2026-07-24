"""Labelled synthetic evaluation for structured financial-note extraction."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.ai.errors import AIError, AIOutputError, AIProviderError
from app.ai.extraction import (
    ExtractedFinancialEvent,
    FinancialNoteExtractor,
    NoteExtractionContext,
)
from app.ai.prompts.financial_note_v1 import PROMPT_NAME, PROMPT_VERSION, SCHEMA_VERSION
from app.domain.enums import NormalizedEventKind, RecurrenceRule
from app.domain.normalization import normalize_display_text
from app.ledger.commands import parse_currency
from app.ledger.errors import LedgerValidationError
from app.ledger.periods import parse_timezone

DATASET_VERSION = "financial-notes/v1"
_SCORED_FIELDS = (
    "event_kind",
    "amount",
    "currency",
    "merchant_name",
    "counterparty",
    "occurred_local_date",
    "due_date",
    "recurrence_rule",
    "next_expected_date",
    "category_hint",
)
_OPTIONAL_FACT_FIELDS = _SCORED_FIELDS[1:]


class ExpectedExtraction(BaseModel):
    """Human-labelled facts; explicit nulls mean the source does not support a value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_kind: NormalizedEventKind
    amount: Decimal | None
    currency: str | None
    merchant_name: str | None
    counterparty: str | None
    occurred_local_date: date | None
    due_date: date | None
    recurrence_rule: RecurrenceRule | None
    next_expected_date: date | None
    category_hint: str | None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return parse_currency(value)
        except LedgerValidationError as exc:
            raise ValueError("expected currency is not supported") from exc

    @field_validator(
        "merchant_name",
        "counterparty",
        "category_hint",
        mode="before",
    )
    @classmethod
    def normalize_expected_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = normalize_display_text(value)
        return normalized or None

    @model_validator(mode="after")
    def validate_money_pair(self) -> Self:
        if (self.amount is None) != (self.currency is None):
            raise ValueError("expected amount and currency must both be known or both be null")
        return self


class ExtractionEvaluationCase(BaseModel):
    """One synthetic note plus trusted context and labelled expected output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    note: str = Field(min_length=1, max_length=8_000)
    source_timestamp: datetime
    timezone: str
    default_currency: str
    slices: tuple[str, ...] = Field(min_length=1, max_length=12)
    expected: ExpectedExtraction

    @field_validator("source_timestamp")
    @classmethod
    def require_aware_source_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source_timestamp must include a timezone offset")
        return value

    @field_validator("timezone")
    @classmethod
    def require_timezone(cls, value: str) -> str:
        try:
            parse_timezone(value)
        except LedgerValidationError as exc:
            raise ValueError("timezone is not recognized") from exc
        return value

    @field_validator("default_currency")
    @classmethod
    def require_default_currency(cls, value: str) -> str:
        try:
            return parse_currency(value)
        except LedgerValidationError as exc:
            raise ValueError("default_currency is not supported") from exc

    @field_validator("slices")
    @classmethod
    def normalize_slices(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip().casefold() for item in value if item.strip()))
        if not normalized:
            raise ValueError("at least one non-blank evaluation slice is required")
        return normalized


@dataclass(frozen=True, slots=True)
class LoadedExtractionDataset:
    """Validated cases plus the exact content hash used for a benchmark run."""

    cases: tuple[ExtractionEvaluationCase, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class PredictionScore:
    """Per-case correctness without retaining private note text."""

    correctness: dict[str, bool]
    unsupported_fields: tuple[str, ...]


def load_extraction_dataset(path: Path) -> LoadedExtractionDataset:
    """Load strict JSONL, rejecting duplicate IDs and invalid contexts."""
    content = path.read_bytes()
    cases: list[ExtractionEvaluationCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            case = ExtractionEvaluationCase.model_validate_json(raw_line)
        except ValidationError as exc:
            raise ValueError(f"invalid extraction dataset row {line_number}") from exc
        if case.id in seen_ids:
            raise ValueError(f"duplicate extraction dataset id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError("extraction evaluation dataset is empty")
    return LoadedExtractionDataset(
        cases=tuple(cases),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def score_prediction(
    case: ExtractionEvaluationCase,
    event: ExtractedFinancialEvent,
) -> PredictionScore:
    """Compare deterministic fields and count invented optional facts."""
    actual = {
        "event_kind": event.event_kind,
        "amount": event.amount,
        "currency": event.currency,
        "merchant_name": event.merchant_name,
        "counterparty": event.counterparty,
        "occurred_local_date": (
            event.occurred_at.astimezone(ZoneInfo(case.timezone)).date()
            if event.occurred_at is not None
            else None
        ),
        "due_date": event.due_date,
        "recurrence_rule": event.recurrence_rule,
        "next_expected_date": event.next_expected_date,
        "category_hint": event.category_hint,
    }
    expected = case.expected.model_dump()
    correctness: dict[str, bool] = {}
    for field in _SCORED_FIELDS:
        predicted_value = actual[field]
        expected_value = expected[field]
        if field in {"merchant_name", "counterparty", "category_hint"}:
            correctness[field] = _normalized_text(predicted_value) == _normalized_text(
                expected_value
            )
        else:
            correctness[field] = predicted_value == expected_value
    unsupported = tuple(
        field
        for field in _OPTIONAL_FACT_FIELDS
        if expected[field] is None and actual[field] is not None
    )
    return PredictionScore(
        correctness=correctness,
        unsupported_fields=unsupported,
    )


async def evaluate_extraction_dataset(
    dataset: LoadedExtractionDataset,
    extractor: FinancialNoteExtractor,
    *,
    configured_provider: str,
    configured_model: str,
) -> dict[str, Any]:
    """Run the real extraction boundary and emit content-free aggregate diagnostics."""
    field_totals = {field: 0 for field in _SCORED_FIELDS}
    field_correct = {field: 0 for field in _SCORED_FIELDS}
    slice_cases: dict[str, int] = defaultdict(int)
    slice_valid: dict[str, int] = defaultdict(int)
    slice_field_totals: dict[str, int] = defaultdict(int)
    slice_field_correct: dict[str, int] = defaultdict(int)
    cases_report: list[dict[str, Any]] = []
    schema_valid = 0
    provider_failures = 0
    output_failures = 0
    unsupported_count = 0
    expected_null_count = 0
    latency_ms_total = 0
    input_tokens_total = 0
    output_tokens_total = 0
    observed_provider = configured_provider
    observed_model = configured_model

    for case in dataset.cases:
        for slice_name in case.slices:
            slice_cases[slice_name] += 1
        expected_values = case.expected.model_dump()
        expected_null_count += sum(
            expected_values[field] is None for field in _OPTIONAL_FACT_FIELDS
        )
        try:
            result = await extractor.extract(
                case.note,
                NoteExtractionContext(
                    source_timestamp=case.source_timestamp,
                    timezone=case.timezone,
                    default_currency=case.default_currency,
                ),
            )
        except AIError as exc:
            if isinstance(exc, AIProviderError):
                provider_failures += 1
            elif isinstance(exc, AIOutputError):
                output_failures += 1
            cases_report.append(
                {
                    "id": case.id,
                    "status": "failed",
                    "error_code": exc.code,
                    "incorrect_fields": list(_SCORED_FIELDS),
                    "unsupported_fields": [],
                }
            )
            for field in _SCORED_FIELDS:
                field_totals[field] += 1
            for slice_name in case.slices:
                slice_field_totals[slice_name] += len(_SCORED_FIELDS)
            continue

        schema_valid += 1
        observed_provider = result.telemetry.provider
        observed_model = result.telemetry.model
        latency_ms_total += result.telemetry.latency_ms
        input_tokens_total += result.telemetry.input_tokens or 0
        output_tokens_total += result.telemetry.output_tokens or 0
        score = score_prediction(case, result.event)
        incorrect_fields = [
            field for field, is_correct in score.correctness.items() if not is_correct
        ]
        unsupported_count += len(score.unsupported_fields)
        for field, is_correct in score.correctness.items():
            field_totals[field] += 1
            field_correct[field] += int(is_correct)
        for slice_name in case.slices:
            slice_valid[slice_name] += 1
            slice_field_totals[slice_name] += len(_SCORED_FIELDS)
            slice_field_correct[slice_name] += sum(score.correctness.values())
        cases_report.append(
            {
                "id": case.id,
                "status": "scored",
                "error_code": None,
                "incorrect_fields": incorrect_fields,
                "unsupported_fields": list(score.unsupported_fields),
            }
        )

    field_metrics = {
        field: _metric(field_correct[field], field_totals[field]) for field in _SCORED_FIELDS
    }
    all_correct = sum(field_correct.values())
    all_total = sum(field_totals.values())
    macro_accuracy = sum(metric["accuracy"] for metric in field_metrics.values()) / len(
        field_metrics
    )
    slice_metrics = {
        slice_name: {
            "cases": count,
            "schema_valid_rate": _ratio(slice_valid[slice_name], count),
            "micro_field_accuracy": _ratio(
                slice_field_correct[slice_name],
                slice_field_totals[slice_name],
            ),
        }
        for slice_name, count in sorted(slice_cases.items())
    }
    return {
        "dataset": {
            "version": DATASET_VERSION,
            "sha256": dataset.sha256,
            "case_count": len(dataset.cases),
        },
        "contract": {
            "prompt_name": PROMPT_NAME,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "provider": observed_provider,
            "model": observed_model,
        },
        "quality": {
            "schema_valid": schema_valid,
            "schema_valid_rate": _ratio(schema_valid, len(dataset.cases)),
            "provider_failures": provider_failures,
            "output_failures": output_failures,
            "field_metrics": field_metrics,
            "micro_field_accuracy": _ratio(all_correct, all_total),
            "macro_field_accuracy": round(macro_accuracy, 4),
            "unsupported_non_null_count": unsupported_count,
            "unsupported_non_null_rate": _ratio(
                unsupported_count,
                expected_null_count,
            ),
        },
        "usage": {
            "latency_ms_total": latency_ms_total,
            "input_tokens_total": input_tokens_total,
            "output_tokens_total": output_tokens_total,
        },
        "slices": slice_metrics,
        "cases": cases_report,
    }


def report_json(report: dict[str, Any]) -> str:
    """Serialize metrics deterministically for review or artifact storage."""
    return json.dumps(report, indent=2, sort_keys=True)


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("text evaluation fields must be strings or null")
    normalized = normalize_display_text(value).casefold()
    return normalized or None


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _metric(correct: int, evaluated: int) -> dict[str, int | float]:
    return {
        "evaluated": evaluated,
        "correct": correct,
        "accuracy": _ratio(correct, evaluated),
    }
