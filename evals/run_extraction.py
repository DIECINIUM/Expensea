"""Run the labelled synthetic extraction evaluation against configured AI."""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
from pathlib import Path

from app.ai.evaluation import (
    evaluate_extraction_dataset,
    load_extraction_dataset,
    report_json,
)
from app.ai.extraction import FinancialNoteExtractor
from app.ai.factory import create_structured_provider
from app.core.config import Settings


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate configured structured extraction on synthetic labelled notes.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/extraction/v1.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. Notes are never written to the report.",
    )
    return parser.parse_args()


async def _run(arguments: argparse.Namespace) -> int:
    settings = Settings()
    dataset = load_extraction_dataset(arguments.dataset)
    extractor = FinancialNoteExtractor(
        create_structured_provider(settings),
        max_input_chars=settings.ai_max_input_chars,
        review_confidence_threshold=Decimal(
            str(settings.ai_review_confidence_threshold)
        ),
    )
    report = await evaluate_extraction_dataset(
        dataset,
        extractor,
        configured_provider=settings.ai_provider.value,
        configured_model=settings.ai_model,
    )
    rendered = report_json(report)
    print(rendered)
    if arguments.output is not None:
        arguments.output.write_text(f"{rendered}\n", encoding="utf-8")
    return 0


def main() -> int:
    """CLI entry point."""
    return asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    raise SystemExit(main())
