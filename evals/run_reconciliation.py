"""Run deterministic reconciliation against the labelled synthetic dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.reconciliation.evaluation import (
    evaluate_reconciliation_dataset,
    load_reconciliation_dataset,
    reconciliation_report_json,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate deterministic reconciliation on labelled source pairs.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/reconciliation/v1.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. Source descriptions are never written.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    arguments = _arguments()
    dataset = load_reconciliation_dataset(arguments.dataset)
    rendered = reconciliation_report_json(evaluate_reconciliation_dataset(dataset))
    print(rendered)
    if arguments.output is not None:
        arguments.output.write_text(f"{rendered}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
