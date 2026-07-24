# Phase 4 deterministic reconciliation

## Goal

Prevent repeated representations of one purchase from inflating the ledger while
preserving every source event and making uncertain matches reviewable.

```text
normalized source event
  → owner-scoped candidate lookup
  → explainable deterministic score
  → merge | possible duplicate | new transaction
  → evidence + append-only decision audit
```

Reconciliation never asks an LLM to decide whether money is duplicated.

## Acceptance behavior

Given an existing posted expense:

```text
₹480 · Swiggy · 20:31
```

a second source representation with the same currency, amount, compatible event type,
nearby time, and strongly matching merchant/description must attach its evidence to
the existing transaction. Spending remains ₹480.

A weaker match above the possible-duplicate threshold must:

1. create no transaction;
2. create no evidence link yet;
3. remain in `needs_review`;
4. expose both representations, score, and reasons to the owner; and
5. require an explicit merge or keep-separate action.

An event below that threshold creates a new transaction and retains its own evidence.

## Candidate boundary

Candidate lookup is always scoped by the authenticated `user_id` and requires:

- posted status;
- compatible transaction type;
- exact decimal amount;
- exact currency; and
- either timestamp proximity or an overlapping typed payment identifier.

Typed identifiers use bounded canonical values such as:

```text
upi:123456789012
bank_ref:abc123
card_auth:xyz789
```

An identifier match cannot override an amount, currency, type, ownership, or status
mismatch. Candidate lookup is capped and indexed. A PostgreSQL transaction advisory
lock serializes reconciliation writes per user so concurrent source deliveries cannot
both create canonical transactions before seeing each other.

## Explainable scoring

The initial score uses four deterministic signals:

| Signal | Default weight |
| --- | ---: |
| Exact amount and currency | 0.35 |
| Timestamp proximity inside the configured window | 0.25 |
| Normalized merchant similarity | 0.20 |
| Normalized description similarity | 0.20 |

Weights, candidate window, candidate cap, and decision thresholds are validated
configuration. Weights must sum to exactly `1.0`; the possible-duplicate threshold
must be lower than the auto-merge threshold.

Text similarity uses normalized deterministic strings and tokens. It is not semantic
embedding search. An exact overlapping typed payment identifier plus matching money
and type returns a score of `1.0000` with an explicit identifier reason.

Default decisions:

```text
score >= 0.92             merge
0.70 <= score < 0.92      possible_duplicate
score < 0.70              new_transaction
```

These are conservative starting values to be measured against the committed labelled
dataset. They are not claims of production calibration.

## Review and audit lifecycle

Every normalized transaction event gets one `ReconciliationCase`. Its initial
decision, score, scoring version, reasons, candidate, and resulting transaction are
retained.

Every state change also appends a `ReconciliationAction`:

- `candidate_flagged`;
- `auto_merged`;
- `created_new`;
- `user_merged`;
- `user_kept_separate`; or
- `user_unmerged`.

Action rows are insert-only through application services. GraphQL exposes owner-scoped
cases and action history but never raw source payloads.

Unmerge is allowed only for a currently merged case. It creates a new deterministic
transaction from the already validated normalized event, repoints only that event's
evidence to the new transaction, and records the previous and resulting transaction
IDs. It does not delete or mutate the original candidate transaction.

## AI proposal interaction

Approving an AI transaction proposal still passes through reconciliation:

- merge/new outcomes complete proposal approval normally;
- an ambiguous outcome moves the proposal to `reconciliation_review` without a
  canonical target;
- resolving the reconciliation case completes the proposal and raw-event processing
  state atomically.

Receivables, payables, and recurring-payment proposals are not transaction duplicate
candidates in this phase.

## Evaluation

`evals/reconciliation/v1.jsonl` contains labelled duplicate and non-duplicate pairs.
The pure evaluator reports:

- precision, recall, and F1 for automatic merge;
- possible-duplicate review rate;
- false merges;
- false-new decisions; and
- metrics by identifier, merchant, description, and time-distance slices.

False merges are treated as more costly than missed duplicates. No threshold is
promoted from this small synthetic dataset without broader representative evidence.

## Security and privacy

- Candidate queries and every foreign key are owner-scoped.
- Browser input never selects a user ID.
- Raw email/note content, tokens, and model reasoning are not added to reconciliation
  rows or logs.
- Scores and reason codes are deterministic and content-bounded.
- Ambiguity fails to review, never to a silent merge.
- Evidence is preserved for every source representation.

## Verification

Phase 4 is complete only when:

```text
make check
make eval-reconciliation

alembic upgrade head
alembic downgrade 20260724_0005
alembic upgrade head
```

and tests prove automatic merge, ambiguous review, keep-separate, unmerge, replay,
concurrent delivery, cross-user isolation, evidence preservation, GraphQL errors, and
frontend review behavior.
