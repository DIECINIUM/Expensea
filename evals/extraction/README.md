# Financial-note extraction evaluation

`v1.jsonl` contains 24 synthetic, human-labelled notes. It includes every supported
event kind, missing facts, Indian number notation, relative dates across timezones
and daylight-saving transitions, prompt injection, and multi-event ambiguity.

This is a regression and smoke benchmark, not a statistically representative quality
claim. Expected `null` values are intentional: a non-null prediction is counted as an
unsupported fact. Relative dates are scored as user-local calendar dates because a
note such as “yesterday” does not support an exact time of day.

Run the configured provider from the repository root:

```bash
make eval-extraction
```

Or retain a content-free JSON report:

```bash
set -a
. ./.env
set +a
PYTHONPATH=apps/api .venv/bin/python evals/run_extraction.py \
  --dataset evals/extraction/v1.jsonl \
  --output /tmp/spendgraph-extraction-eval.json
```

The report includes case IDs, error codes, aggregate metrics, and incorrect field
names. It never includes the note text. Do not enable automatic financial posting
from results on this small dataset.
