# SpendGraph AI

SpendGraph AI is a deterministic personal-finance ledger built around one rule:

> **AI may interpret; deterministic software controls money.**

## Project status

**Phases 1 and 2 are complete, and the review-first Phase 3 slice is
implemented.** The repository now contains:

- exact-decimal transactions with merchants and categories;
- per-currency monthly, category, and merchant summaries;
- people, receivables, payables, partial settlements, and outstanding balances;
- manually managed recurring payments and recorded occurrences;
- immutable raw events, normalized events, evidence, and replay-safe ingestion;
- manual-note, mock-receipt, bounded CSV, Gmail receipt, and Google Keep Takeout
  connector adapters;
- schema-constrained natural-language extraction through a provider-neutral AI
  boundary;
- persisted proposals with model/prompt metadata and explicit approve/reject
  transitions;
- a dashboard AI inbox with informal-note input, Keep JSON import, tags, category
  suggestions, review reasons, and canonical-ledger refresh;
- an owner-scoped Strawberry GraphQL API;
- a live React/Apollo dashboard with mutation-and-refresh flows; and
- reversible PostgreSQL migrations plus an idempotent development seed.

AI output never posts itself. It remains an untrusted proposal until an authenticated
user approves it and deterministic services revalidate and create the canonical
transaction, obligation, or recurring payment. Reconciliation, personalized
categorization, the read-only finance agent, and production Gmail OAuth remain later
phases.

## Run it with Docker

### macOS prerequisites

1. Install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/).
2. Start Docker Desktop and wait until it reports that the engine is running.
3. Verify the installation:

   ```bash
   docker --version
   docker compose version
   ```

4. Install Make if it is not already available. Apple's command-line tools include
   it:

   ```bash
   xcode-select --install
   ```

Node.js and Python are not required for the standard Docker runtime.

### Fresh clone

```bash
git clone https://github.com/DIECINIUM/Expensea.git
cd Expensea
make env
make dev
```

The first startup builds the images, waits for PostgreSQL, applies all Alembic
migrations, creates the development demo ledger once, starts the API, and then
starts the web app.

Open:

- web dashboard: <http://localhost:5173>
- API health: <http://localhost:8000/health>
- GraphQL endpoint: <http://localhost:8000/graphql>

Stop the stack without deleting its database:

```bash
make stop
```

The default demo ledger is controlled by `DEMO_SEED_ENABLED=true` in `.env`. Set it
to `false` before the first startup for an empty ledger. The seed is idempotent: if
the configured development profile already exists, it leaves every row unchanged.
It refuses to run outside the development environment.

## Configure AI extraction

The repository-safe default is `AI_PROVIDER=disabled`, so every clone can run the
deterministic ledger without an AI server. To enable the financial-note and Google
Keep extraction workflow, edit the ignored local `.env`:

```dotenv
AI_PROVIDER=ollama
AI_BASE_URL=http://your-ollama-compatible-host:11434
AI_MODEL=gemma4:e4b
AI_REQUEST_TIMEOUT_SECONDS=120
```

Use only the origin in `AI_BASE_URL`; the API appends `/api/chat`. If Ollama runs
directly on the same Mac while SpendGraph runs in Docker, use
`http://host.docker.internal:11434` rather than container-local `127.0.0.1`.

Never commit a private host, access token, or `.env`. AI configuration is
server-only and is never exposed through a `VITE_*` browser variable.

After restarting `make dev`, use **AI inbox → Extract a quick note**. The dashboard
will display the proposed kind, exact amount/currency, merchant or counterparty,
category suggestion, tags, confidence, and deterministic review reasons.

For Google Keep:

1. export notes with Google Takeout;
2. choose an individual note `.json` file in the AI inbox; and
3. approve or reject the extracted proposal.

The import ignores attachments and trashed/empty notes and accepts at most 64 KiB per
note. The Gmail adapter uses the official read-only API path and filters likely
financial messages, but account connection is deliberately unavailable until secure
OAuth state/PKCE, encrypted token storage, revocation, and deployment credentials
are implemented in Phase 8.

## What migrations do

A migration is a versioned database-schema change. In this project Alembic
migrations create the ledger tables, foreign keys, checks, indexes, triggers, and
system categories. They let every clone construct the same database in a reviewed,
repeatable order.

`make dev` applies pending migrations automatically. They can also be run explicitly:

```bash
make migrate
```

To apply migrations and run the development seed without starting the complete
stack:

```bash
make bootstrap
```

To run only the idempotent seed:

```bash
make seed
```

Routine commands preserve the `spendgraph_postgres_data` named volume. PostgreSQL
initialization variables only affect an empty volume; editing the database
user/password/name later does not rewrite an existing database.

## Implemented behavior

### Money

- API amounts are decimal strings, never JSON floats.
- Python uses `Decimal`; PostgreSQL uses `NUMERIC(19, 4)`.
- Amounts must be positive, finite, and no more precise than four fractional digits.
- Every monetary record has an explicit supported currency.
- Totals are separated by currency; there is no implicit exchange-rate conversion.

### Transactions and summaries

- Spending is posted `expense` plus posted `shared_expense`, less posted `refund`.
- Income is posted `income`.
- Transfers, pending transactions, and voided transactions do not affect those
  totals.
- User-local calendar months are converted to half-open UTC ranges.
- Transaction timelines use stable keyset cursors.

### Obligations

- A receivable is money owed to the ledger owner.
- A payable is money the owner owes.
- Settlements are immutable append-only rows.
- Partial and full settlements update status atomically.
- Overpayment is rejected and rolled back.
- Overdue state is derived from the owner's date and the due date.

### Recurring payments

- Recurring payments support weekly, monthly, quarterly, and yearly schedules.
- Active schedules contribute to upcoming totals.
- Recording the expected occurrence creates one posted expense and advances the
  schedule atomically.
- Stale or duplicate occurrence recording is rejected.

### Ownership and errors

- The browser never chooses a `user_id`; the server injects the authenticated
  principal.
- Every user-owned repository query includes that principal.
- Foreign and absent IDs have the same public not-found behavior.
- GraphQL applies depth/complexity limits and returns typed, client-safe domain
  problems.
- The current identity provider is deliberately development-only, not production
  authentication.

### Ingestion and AI review

- Source identity or a canonical content hash makes delivery replay-safe.
- Minimized raw source data and mutable processing state are stored separately.
- Canonical transactions and their evidence links commit atomically.
- Manual and Keep notes become schema-validated proposals, never direct writes.
- Approval uses existing deterministic ledger/obligation/recurring repositories.
- Rejection creates no canonical financial record.
- Provider failures preserve the raw event for a later retry.
- Model reasoning traces, raw OAuth tokens, full Gmail addresses, and attachments are
  not persisted.

See [Phase 1 ledger](docs/phase1-ledger.md),
[Phase 2 ingestion](docs/phase2-ingestion.md), [AI design](docs/ai-design.md), and
[Data model](docs/data-model.md) for the complete contract.

## Architecture

```text
React dashboard
  → Apollo POST /graphql through the Vite same-origin proxy
    → FastAPI / Strawberry GraphQL delivery adapters
      → owner-scoped ledger / ingestion / proposal services
        → connector and schema-constrained AI ports
          → repositories and deterministic calculations
            → PostgreSQL
```

Resolvers map typed input and output. They do not contain SQL, financial arithmetic,
or transaction boundaries. Services validate commands and own state transitions;
repositories own persistence queries; database constraints provide the final
integrity layer.

The project remains a modular monolith. Connector implementations satisfy one
fetch/normalize/health contract and register by stable key, so future authorized
applications can be added without provider conditionals in ledger code. The finance
agent remains deferred until its deterministic read-only tools and evaluations exist.

## GraphQL capabilities

The current API includes:

- profile, categories, merchants, transactions, and stable pagination;
- financial, category, merchant, and monthly summaries;
- people, receivables, payables, settlements, and obligation summaries;
- recurring-payment schedules and upcoming summaries; and
- typed mutations for manual transactions, categories, people, obligations,
  settlements, recurring status transitions, and recording occurrences;
- pending financial-event proposals;
- manual financial-note and Google Keep note extraction; and
- locked proposal approval/rejection with typed client-safe errors.

GraphiQL is available in validated debug environments at the GraphQL endpoint.

## Development commands

| Action | Command |
| --- | --- |
| Create `.env` without overwriting an existing file | `make env` |
| Start the complete Docker development stack | `make dev` |
| Stop containers and preserve PostgreSQL data | `make stop` |
| Start only PostgreSQL | `make db-up` |
| Apply migrations in Docker | `make migrate` |
| Apply migrations and seed the development ledger | `make bootstrap` |
| Re-run the idempotent development seed | `make seed` |
| Verify the web-to-GraphQL foundation path | `make smoke` |
| Install local Python and Node dependencies | `make setup` |
| Run backend and frontend tests | `make test` |
| Run linters and formatting checks | `make lint` |
| Run strict Python and TypeScript checks | `make typecheck` |
| Build the web production bundle | `make build` |
| Run dependency audits | `make audit` |
| Run the aggregate local gate | `make check` |

Local, non-container processes require Python 3.12+, Node.js 24+, and `make setup`.
Start them in separate terminals with:

```bash
make db-up
make migrate
make dev-api
make dev-web
```

## Verification

The latest local verification includes:

- 152 PostgreSQL-enabled backend tests plus one separately executed opt-in live AI
  contract test against the configured provider;
- strict mypy, Ruff lint, and Ruff formatting checks;
- 32 frontend tests, ESLint, Prettier, strict TypeScript, and a Vite production
  build;
- Alembic upgrade/downgrade/re-upgrade coverage;
- Compose configuration validation; and
- migration and idempotent seeding from a separate empty Docker volume.

GitHub Actions repeats backend, frontend, migration, smoke, container, dependency,
and full-history secret-scanning gates. A point-in-time local result does not replace
the remote checks for a pushed commit.

## Repository layout

```text
.
├── .github/                  # CI and dependency update policy
├── apps/
│   ├── api/                  # FastAPI, GraphQL, services, models, migrations, tests
│   └── web/                  # React dashboard, Apollo operations, tests
├── docs/
│   ├── adr/                  # Architecture decisions
│   ├── architecture.md
│   ├── data-model.md
│   ├── ai-design.md
│   ├── phase1-ledger.md
│   ├── phase2-ingestion.md
│   ├── security.md
│   └── implementation-checklist.md
├── evals/                    # Later AI/reconciliation evaluation fixtures
├── packages/shared/          # Future shared/generated contracts
├── scripts/
├── docker-compose.yml
└── Makefile
```

`docs/interview-notes.md` is intentionally local-only and ignored by Git.

## Roadmap

| Phase | Capability | Status |
| --- | --- | --- |
| 0 | Monorepo, health contracts, tooling, CI, PostgreSQL foundation | Complete |
| 1 | Deterministic ledger, obligations, recurring payments, live dashboard | **Complete** |
| 2 | Raw events, evidence, connector contract, replay-safe ingestion | **Complete** |
| 3 | Structured natural-language extraction and review | In progress: end-to-end review slice implemented; evaluation pending |
| 4 | Duplicate reconciliation | Planned |
| 5 | Personalized categorization and correction memory | Planned |
| 6 | Extended deterministic analytics and grounded explanations | Planned |
| 7 | Read-only finance agent over typed service tools | Planned |
| 8+ | Authorized external connectors and production hardening | Planned |

The detailed source of truth is the
[implementation checklist](docs/implementation-checklist.md).
