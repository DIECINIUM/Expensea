# Evaluations

Executable evaluation assets are versioned with the capability they measure:

- [`extraction/v1.jsonl`](extraction/v1.jsonl) measures structured financial-note
  extraction, missing-fact preservation, prompt injection, and relative dates.
- [`reconciliation/v1.jsonl`](reconciliation/v1.jsonl) measures deterministic
  automatic merges, conservative review, identifier guards, and false-merge risk.

Categorization and finance-agent datasets are introduced with their respective
phases. No benchmark number is reported before its committed harness is run, and
small synthetic datasets are never represented as production quality.
