# Reconciliation evaluation

`v1.jsonl` contains 24 synthetic, human-labelled source/candidate pairs. It covers
exact and similar text, typed payment identifiers, time-distance bands, repeated
purchases, missing merchants, refunds, and amount/currency/type safety guards.

Run the pure deterministic scorer from the repository root:

```bash
make eval-reconciliation
```

Or retain a source-content-free JSON report:

```bash
PYTHONPATH=apps/api .venv/bin/python evals/run_reconciliation.py \
  --dataset evals/reconciliation/v1.jsonl \
  --output /tmp/spendgraph-reconciliation-eval.json
```

The report contains case IDs, labels, decisions, scores, reason codes, aggregate
automatic-merge precision/recall/F1, review rate, false merges, false-new decisions,
and slice metrics. It deliberately omits descriptions and merchant names.

This small synthetic dataset is a regression harness, not representative production
calibration. False merges are more costly than missed duplicates, so broader
owner-labelled data is required before changing automatic-merge policy.
