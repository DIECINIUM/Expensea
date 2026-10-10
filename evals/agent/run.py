#!/usr/bin/env python3
"""Run the fixed, synthetic read-only finance-agent regression benchmark."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.agent.evaluation import EvaluationCase, evaluate  # noqa: E402


def main() -> int:
    dataset = json.loads((ROOT / "evals" / "datasets" / "agent-v1.json").read_text())
    cases = tuple(EvaluationCase.model_validate(case) for case in dataset)
    report = asyncio.run(evaluate(cases))
    print(json.dumps({"synthetic_only": True, **asdict(report)}, indent=2))
    return int(bool(report.failed_case_ids))


if __name__ == "__main__":
    raise SystemExit(main())
