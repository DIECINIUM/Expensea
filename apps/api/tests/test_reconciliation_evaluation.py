"""Regression tests for the labelled reconciliation evaluation harness."""

import json
from pathlib import Path

import pytest

from app.domain.enums import ReconciliationDecision
from app.reconciliation.evaluation import (
    LoadedReconciliationDataset,
    evaluate_reconciliation_dataset,
    load_reconciliation_dataset,
    reconciliation_report_json,
)

DATASET_PATH = Path(__file__).parents[3] / "evals" / "reconciliation" / "v1.jsonl"


def test_versioned_dataset_is_strict_and_all_expected_routes_match() -> None:
    dataset = load_reconciliation_dataset(DATASET_PATH)

    report = evaluate_reconciliation_dataset(dataset)

    assert len(dataset.cases) == 24
    assert len(dataset.sha256) == 64
    assert report["dataset"]["case_count"] == 24
    assert report["contract"]["score_version"] == "reconciliation-score/v1"
    assert report["quality"]["expected_decision_accuracy"] == 1.0
    assert report["quality"]["automatic_merge_precision"] == 1.0
    assert report["quality"]["automatic_merge_recall"] == 0.5882
    assert report["quality"]["automatic_merge_f1"] == 0.7407
    assert report["quality"]["false_merges"] == 0
    assert report["quality"]["false_new_decisions"] == 0
    assert report["slices"]["identifier"]["automatic_merge_recall"] == 1.0
    assert report["slices"]["review_safety"]["false_merges"] == 0
    assert all(item["decision_correct"] for item in report["cases"])


def test_report_is_deterministic_and_omits_source_text() -> None:
    report = evaluate_reconciliation_dataset(load_reconciliation_dataset(DATASET_PATH))

    rendered = reconciliation_report_json(report)
    parsed = json.loads(rendered)

    assert parsed == report
    assert "Swiggy dinner order" not in rendered
    assert "merchant_name" not in rendered
    assert rendered == reconciliation_report_json(report)


def test_evaluator_counts_a_labelled_false_merge() -> None:
    original = load_reconciliation_dataset(DATASET_PATH).cases[0]
    unsafe_label = original.model_copy(
        update={
            "id": "synthetic_false_merge",
            "is_duplicate": False,
            "expected_decision": ReconciliationDecision.POSSIBLE_DUPLICATE,
        }
    )
    dataset = LoadedReconciliationDataset(
        cases=(unsafe_label,),
        sha256="synthetic",
    )

    quality = evaluate_reconciliation_dataset(dataset)["quality"]

    assert quality["automatic_merges"] == 1
    assert quality["false_merges"] == 1
    assert quality["automatic_merge_precision"] == 0.0


def test_loader_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    row = DATASET_PATH.read_text(encoding="utf-8").splitlines()[0]
    duplicate_path = tmp_path / "duplicate.jsonl"
    duplicate_path.write_text(f"{row}\n{row}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate reconciliation dataset id"):
        load_reconciliation_dataset(duplicate_path)
