#!/usr/bin/env python3
"""Evaluate the deterministic correction-retrieval baseline."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.categorization.policy import retrieval_assignment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.dataset.read_text().splitlines() if line]
    labels = sorted(
        {
            label
            for case in cases
            for label in [case["expected"], *(item[1] for item in case["memory"])]
            if label is not None
        }
    )
    ids = {
        label: uuid5(NAMESPACE_URL, f"spendgraph-category:{label}") for label in labels
    }
    results: list[tuple[str | None, str | None]] = []
    errors: dict[str, int] = defaultdict(int)
    for case in cases:
        assignment = retrieval_assignment(
            case["description"],
            tuple((description, ids[label]) for description, label in case["memory"]),
        )
        predicted = (
            next(
                label
                for label, category_id in ids.items()
                if category_id == assignment.category_id
            )
            if assignment
            else None
        )
        expected = case["expected"]
        results.append((expected, predicted))
        if expected != predicted:
            errors[
                f"{expected or 'Uncategorized'}->{predicted or 'Uncategorized'}"
            ] += 1

    accuracy = sum(expected == predicted for expected, predicted in results) / len(
        results
    )
    f1_values = []
    for label in [*labels, None]:
        tp = sum(
            expected == label and predicted == label for expected, predicted in results
        )
        fp = sum(
            expected != label and predicted == label for expected, predicted in results
        )
        fn = sum(
            expected == label and predicted != label for expected, predicted in results
        )
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1_values.append(
            2 * precision * recall / (precision + recall) if precision + recall else 0
        )
    report = {
        "dataset": str(args.dataset),
        "cases": len(cases),
        "accuracy": f"{accuracy:.4f}",
        "macro_f1": f"{sum(f1_values) / len(f1_values):.4f}",
        "errors": dict(sorted(errors.items())),
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if accuracy == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
