# Phase 1 deterministic ledger

**Status:** first vertical slice in progress.

## Goal

Replace the Phase 0 financial preview with the smallest complete deterministic
ledger path:

```text
development identity
  → validated manual transaction command
    → tenant-scoped service and repository
      → PostgreSQL NUMERIC ledger row
        → deterministic per-currency summary
          → typed GraphQL response
            → live React dashboard
```

No AI, source connector, reconciliation, or inferred financial fact is part of this
phase.

## Architecture

- SQLAlchemy models and Alembic migrations own the executable relational contract.
- Repositories contain explicit owner-scoped database queries.
- Services own validation, authorization, transaction boundaries, and financial
  calculations.
- GraphQL resolvers translate typed inputs and outputs only; they contain no SQL or
  arithmetic.
- The browser renders server-calculated totals and never substitutes synthetic
  values after an API failure.

## First increment scope

This increment must:

- establish users, merchants, categories, transactions, people, receivables,
  payables, settlement-history, and recurring-payment tables;
- provide a server-selected development identity that cannot be chosen through
  GraphQL input;
- accept manual transactions with positive decimal-string amounts, explicit
  currency, type, status, description, and timezone-aware occurrence time;
- expose owner-scoped transaction lookup and cursor pagination;
- calculate actual spending, income, category totals, and monthly spending with
  documented status/type semantics;
- return separate totals by currency and perform no foreign-exchange conversion;
- replace the dashboard's synthetic financial values with GraphQL ledger data; and
- provide an explicit, idempotent synthetic INR demo seed path.

The database schema reserves the remaining Phase 1 concepts, but people,
receivable/payable settlement workflows, recurring-payment management, and their
dedicated UI are not complete until their service, API, authorization, and state
transition tests pass.

## Money and summary semantics

- Money enters GraphQL as a decimal string and is parsed to Python `Decimal`.
- Floats, non-finite values, non-positive values, values with more than four
  fractional digits, and values outside `NUMERIC(19, 4)` are rejected before SQL.
- Currency uses an uppercase supported ISO 4217 code.
- Actual spending is posted `expense` plus posted `shared_expense`, less posted
  `refund`, inside the user-local half-open month converted to UTC.
- Income is posted `income` only.
- Transfers, pending transactions, and voided transactions do not affect spending
  or income.
- Category totals use the same signed spending semantics; uncategorized spending
  remains explicit.
- Amounts in different currencies are never combined.

## Security contract

- The client never submits a `user_id`.
- Every user-owned repository method requires the authenticated principal ID.
- Looking up an absent ID and another user's ID has the same public result.
- Referenced custom categories must belong to the principal; system categories are
  shared reference data.
- Development identity is allowed only in development and test environments.
- Expected validation failures return bounded client-safe errors. Unexpected
  failures do not expose SQL, parameters, stack traces, or private financial text.

## Acceptance criteria

The first increment is accepted only when:

1. Alembic upgrade, downgrade, and re-upgrade succeed on PostgreSQL.
2. Exact decimal round-trips and database constraints are tested.
3. Cross-user reads and writes are rejected through the same paths used by GraphQL.
4. Cursor pagination has no duplicate or missing rows for a stable dataset.
5. Refund, transfer, pending, voided, multi-currency, category, and timezone summary
   cases are covered.
6. A manual transaction mutation persists once and the subsequent dashboard query
   returns updated deterministic totals.
7. Frontend loading, failure, empty, success, validation, and mutation-refresh
   states are tested without synthetic fallback values.
8. Local quality gates, dependency audits, container builds, the browser-facing
   GraphQL smoke path, full-history secret scanning, and remote CI pass.

## Explicitly deferred

- Natural-language financial notes and all model-provider calls.
- Raw events, evidence, connectors, and ingestion idempotency.
- Reconciliation, categorization prediction, correction memory, and embeddings.
- AI insights, review queues, and the finance agent.
- Production authentication; the development seam is intentionally not a production
  login mechanism.
