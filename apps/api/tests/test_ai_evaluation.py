"""Synthetic extraction dataset and content-free metric tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.ai.evaluation import (
    ExtractionEvaluationCase,
    LoadedExtractionDataset,
    evaluate_extraction_dataset,
    load_extraction_dataset,
    report_json,
    score_prediction,
)
from app.ai.extraction import ExtractedFinancialEvent, FinancialNoteExtractor
from app.ai.mock import MockStructuredProvider

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = REPOSITORY_ROOT / "evals" / "extraction" / "v1.jsonl"


def _case(
    *,
    case_id: str = "synthetic_case",
    note: str = "Paid USD 10 yesterday.",
    timezone: str = "America/New_York",
) -> ExtractionEvaluationCase:
    return ExtractionEvaluationCase.model_validate(
        {
            "id": case_id,
            "note": note,
            "source_timestamp": "2026-03-09T13:00:00Z",
            "timezone": timezone,
            "default_currency": "USD",
            "slices": ["expense", "relative_date"],
            "expected": {
                "event_kind": "expense",
                "amount": "10.0000",
                "currency": "USD",
                "merchant_name": None,
                "counterparty": None,
                "occurred_local_date": "2026-03-08",
                "due_date": None,
                "recurrence_rule": None,
                "next_expected_date": None,
                "category_hint": None,
            },
        }
    )


def test_committed_dataset_is_valid_unique_and_versioned() -> None:
    dataset = load_extraction_dataset(DATASET_PATH)

    assert len(dataset.cases) == 24
    assert len({case.id for case in dataset.cases}) == 24
    assert len(dataset.sha256) == 64
    assert {"relative_date", "prompt_injection", "missing_fact", "dst"}.issubset(
        {slice_name for case in dataset.cases for slice_name in case.slices}
    )


def test_dataset_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    row = DATASET_PATH.read_text(encoding="utf-8").splitlines()[0]
    duplicate_path = tmp_path / "duplicate.jsonl"
    duplicate_path.write_text(f"{row}\n{row}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate extraction dataset id"):
        load_extraction_dataset(duplicate_path)


def test_scoring_compares_decimals_and_user_local_dates() -> None:
    case = _case()
    event = ExtractedFinancialEvent.model_validate(
        {
            "event_kind": "expense",
            "amount": "10",
            "currency": "USD",
            "description": "Synthetic expense",
            "occurred_at": "2026-03-08T16:00:00Z",
            "confidence": "0.9",
        }
    )

    score = score_prediction(case, event)

    assert all(score.correctness.values())
    assert score.unsupported_fields == ()


def test_scoring_counts_non_null_values_for_expected_unknown_facts() -> None:
    values = _case().model_dump(mode="json")
    values["expected"]["amount"] = None
    values["expected"]["currency"] = None
    values["expected"]["occurred_local_date"] = None
    case = ExtractionEvaluationCase.model_validate(values)
    event = ExtractedFinancialEvent.model_validate(
        {
            "event_kind": "expense",
            "amount": "10",
            "currency": "USD",
            "description": "Invented facts",
            "occurred_at": "2026-03-08T16:00:00Z",
            "confidence": "0.9",
        }
    )

    score = score_prediction(case, event)

    assert score.unsupported_fields == (
        "amount",
        "currency",
        "occurred_local_date",
    )


@pytest.mark.asyncio
async def test_evaluator_keeps_notes_out_of_reports_and_scores_failures() -> None:
    secret_note = "Private synthetic marker must not appear in report."
    success_case = _case(case_id="successful_case", note=secret_note)
    failure_case = _case(case_id="failed_case", note="Second private marker.")
    provider = MockStructuredProvider(
        [
            {
                "event_kind": "expense",
                "amount": "10.0000",
                "currency": "USD",
                "description": "Synthetic expense",
                "occurred_at": "2026-03-08T16:00:00Z",
                "confidence": "0.9000",
            }
        ]
    )
    extractor = FinancialNoteExtractor(
        provider,
        max_input_chars=8_000,
        review_confidence_threshold=Decimal("0.8500"),
    )
    dataset = LoadedExtractionDataset(
        cases=(success_case, failure_case),
        sha256="a" * 64,
    )

    report = await evaluate_extraction_dataset(
        dataset,
        extractor,
        configured_provider="mock",
        configured_model="fixture",
    )
    rendered = report_json(report)

    assert report["quality"]["schema_valid"] == 1
    assert report["quality"]["provider_failures"] == 1
    assert report["quality"]["schema_valid_rate"] == 0.5
    assert report["dataset"]["case_count"] == 2
    assert secret_note not in rendered
    assert "Second private marker" not in rendered
    assert "successful_case" in rendered
    assert "MOCK_PROVIDER_EXHAUSTED" in rendered
