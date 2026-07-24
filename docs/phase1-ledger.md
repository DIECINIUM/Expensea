# Phase 1 deterministic ledger

**Status:** complete.

## Delivered vertical slice

```text
development principal
  → validated GraphQL command
    → owner-scoped service transaction
      → repository query
        → PostgreSQL integrity constraints
          → deterministic typed result
            → live Apollo dashboard
```

Phase 1 implements manual transactions, categories, canonical merchants, people,
receivables, payables, immutable settlements, recurring payments, exact summaries,
and the associated web management flows. It contains no model call, connector,
reconciliation, or inferred financial fact.

## Executable boundaries

- Alembic migrations and SQLAlchemy models define nine ledger tables, constraints,
  ownership-aware foreign keys, triggers, indexes, and ten system categories.
- Repositories contain explicit principal-scoped SQLAlchemy queries.
- Services own validation, authorization, database transaction boundaries, state
  transitions, and arithmetic.
- GraphQL resolvers authenticate, parse/map typed values, call services, and sanitize
  failures. They contain no SQL or financial calculations.
- React renders API values and never substitutes financial placeholders after a
  failed request.

## Transactions and summaries

- Amount input is a positive decimal string and is stored as `NUMERIC(19, 4)`.
- Currency is a supported uppercase ISO 4217 code.
- Stored amounts are unsigned; transaction type supplies economic direction.
- Spending is posted `expense` plus posted `shared_expense`, minus posted `refund`.
- Income is posted `income`.
- Transfers, pending records, and voided records affect neither total.
- Category and merchant summaries use the same spending semantics.
- Months are user-local half-open ranges converted to UTC.
- Currencies are returned separately and never combined without an exchange-rate
  subsystem.
- Transactions use stable `(transaction_date, id)` keyset pagination.

## People and obligations

- A person is unique by normalized name inside one owner's ledger.
- Receivables and payables reference a person belonging to that same owner.
- Original principal is immutable.
- Settlement rows are append-only and reference exactly one obligation.
- Settlement currency must match principal currency.
- A row lock serializes concurrent settlements.
- Partial payment produces `partially_paid`; exact completion produces `paid`.
- Overpayment, settlement of terminal records, and invalid cancellation fail
  atomically.
- `overdue` is derived from an open balance, due date, and owner-local current date.
- Cancelling removes the remaining exposure while preserving settlement history.

## Recurring payments

- Manual schedules support weekly, monthly, quarterly, and yearly recurrence.
- Upcoming totals include active schedules inside an inclusive date window.
- Explicit transitions support active ↔ paused and active/paused → ended.
- Ended schedules are terminal.
- Recording an expected occurrence locks the schedule, creates one posted expense,
  and advances the next calendar occurrence in the same transaction.
- A stale or repeated expected date returns a conflict and cannot duplicate spending.

## Authentication and tenancy

- GraphQL input never accepts an effective `user_id`.
- The authentication seam selects a fixed UUID only in development/test.
- Every user-owned service and repository operation receives the principal UUID.
- Composite foreign keys prevent cross-owner obligation links.
- Category triggers prevent transactions from using another owner's custom category.
- Foreign and absent identifiers map to the same public not-found shape.
- Query depth, alias count, and weighted complexity are bounded before execution.
- Expected failures are typed client problems; unexpected failures do not expose
  SQL, parameters, stack traces, or private values.

The development seam is not production login. Staging and production reject it
during settings validation.

## Development bootstrap

`make dev` starts a one-shot Compose service before the API. It:

1. waits for healthy PostgreSQL;
2. applies `alembic upgrade head`; and
3. runs the development-only demo seed when `DEMO_SEED_ENABLED=true`.

The seed creates the configured development profile, five current-month
transactions, one person, a partially settled receivable, an open payable, and one
active recurring payment. The profile UUID is the idempotency marker: a later run
leaves an existing ledger untouched.

Use `make migrate`, `make seed`, or `make bootstrap` to run those steps explicitly.

## Acceptance evidence

The implemented slice is covered by:

- migration upgrade/downgrade/re-upgrade tests against PostgreSQL;
- exact decimal and database-constraint tests;
- owner-isolation tests through services and GraphQL;
- refund, transfer, status, multi-currency, timezone, category, and pagination
  cases;
- serialized partial/full/overpayment settlement tests;
- recurring transition, occurrence, duplicate, and calendar-advance tests;
- GraphQL mutation-to-summary integration tests;
- frontend loading, error, empty, success, validation, and refetch tests; and
- an empty-volume Compose bootstrap followed by a no-op second seed.

Latest local result: 99 backend tests and 30 frontend tests passed, with Ruff,
strict mypy, ESLint, Prettier, TypeScript, and the production web build clean.
Remote CI remains the authority for the pushed commit.

## Explicitly deferred

- production authentication;
- natural-language extraction and all model-provider calls;
- raw events, evidence, connectors, and ingestion idempotency;
- duplicate reconciliation and correction memory;
- inferred recurring detection and AI insights; and
- the finance agent.
