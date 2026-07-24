# Implementation checklist

**Last updated:** 2026-07-24

**Current phase:** Phase 1 complete; Phase 2 implementation started.

**Rule:** implement Phase 1 through bounded vertical slices whose acceptance behavior
is written before code and checked from actual commands.

`[x]` means the artifact is present and reviewed in the repository. `[ ]` means it is
not complete or has not yet been verified. Future-phase boxes are not defects in
the completed Phase 1 scope.

## Global definition of done

For each material feature:

- [ ] acceptance behavior is written before implementation;
- [ ] business rules live outside GraphQL resolvers and UI components;
- [ ] boundary, domain, and authorization tests cover the new behavior;
- [ ] relevant unit/integration/E2E tests pass;
- [ ] lint, formatting, and strict type checks pass;
- [ ] migrations and rollback/forward impact are reviewed;
- [ ] privacy, threat model, logs, and failure modes are reviewed;
- [ ] observability is sufficient to diagnose failures without private-content logs;
- [ ] public documentation reflects what is actually implemented; and
- [ ] performance/evaluation claims cite a real command and result.

## Phase 0 — planning and foundation

### Goal

Create a reproducible modular-monolith foundation with typed web and API boundaries.
The web executes a same-origin Apollo `health`/`appInfo` query through the Vite
development proxy and exposes honest loading/online/offline states. Financial
dashboard values remain synthetic. No ledger or AI behavior is in scope.

### Repository and developer experience

- [x] Monorepo folders for `apps/api`, `apps/web`, `docs`, `evals`, and
  `packages/shared`.
- [x] Git ignore, editor, line-ending, Python-version, and Node-version files.
- [x] Root `.env.example` with local-only non-secret defaults.
- [x] Make targets for environment creation, install, development, database,
  migrations, dependency locks/audits, tests, lint, type checks, build, and aggregate
  checks.
- [x] `make smoke` owns the local web-to-Vite-proxy-to-GraphQL contract and cleans up
  its processes; `make stop` preserves Compose data.
- [x] Single PostgreSQL component contract with host and optional validated
  `DATABASE_URL` override documented.
- [x] Dockerfiles for API and web development.
- [x] Docker Compose services with PostgreSQL health/dependency checks.
- [x] Compose publishes ports to loopback by default and uses granular web source
  mounts without shadowing container dependencies.
- [x] PostgreSQL named-volume initialization/recovery semantics documented; routine
  commands never imply automatic volume deletion.
- [x] Python production/development locks and npm lock committed; normal setup
  installs from locks.

### Backend foundation

- [x] Python 3.12+ package with FastAPI, Pydantic settings, Strawberry GraphQL,
  SQLAlchemy 2.x, psycopg, and Alembic.
- [x] Configuration fails clearly for invalid settings.
- [x] Settings safely derive/encode the PostgreSQL DSN and validate a full override.
- [x] Exact CORS validation rejects wildcard/credential/path/query origins.
- [x] Deployed environments reject debug; production rejects local/development
  database and CORS defaults.
- [x] Structured path-only logging avoids query strings and private payloads.
- [x] Generic unexpected-error response preserves request ID and CORS headers.
- [x] REST health endpoint.
- [x] GraphQL `health` and `appInfo` query with GET execution disabled.
- [x] GraphQL context seam for future authenticated request context.
- [x] Application-factory-owned lazy async database/session resource without queries
  in resolvers; SQL parameters are hidden.
- [x] Alembic baseline migration.
- [x] pytest tests for configuration and system API boundaries.
- [x] Ruff formatting/lint policy and strict mypy configuration.

### Frontend foundation

- [x] React, strict TypeScript, Vite, Tailwind CSS, and Apollo Client scaffold.
- [x] Same-origin `/graphql` client default and configurable Vite API proxy target.
- [x] App-level provider boundary.
- [x] Dashboard-oriented Phase 0 interface clearly uses demo/placeholder data.
- [x] Apollo foundation query displays loading, online application metadata, and
  retryable offline states.
- [x] Component tests cover successful metadata, loading, and offline behavior.
- [x] Vitest and React Testing Library tests.
- [x] ESLint, Prettier, TypeScript, test, and production-build scripts.

### Automation and documentation

- [x] GitHub Actions backend lint/type/test/audit job with PostgreSQL
  upgrade/downgrade/upgrade migration cycle.
- [x] GitHub Actions frontend lint/format/type/test/build/runtime-audit job.
- [x] GitHub Actions web-to-API smoke job using the local `make smoke` contract.
- [x] GitHub Actions Compose validation and API/web container-build job.
- [x] GitHub Actions full-history gitleaks job.
- [x] Third-party Actions pinned to immutable SHAs with read-only repository
  permission.
- [x] Dependabot configured for Python, npm, Actions, and Docker.
- [x] README with problem, solution, status, architecture, setup, demo, security,
  trade-offs, and roadmap.
- [x] Architecture plan and explicit implemented/planned labels.
- [x] Conceptual Phase 1 data model.
- [x] AI design marked as not implemented.
- [x] Prompt-injection and application-security threat model.
- [x] Six initial ADRs.
- [x] Placeholder evaluation structure without fabricated metrics.

### Verification required before Phase 0 is complete

- [x] `make env` creates `.env` only when absent and does not overwrite local values
  (verified twice with an unchanged checksum).
- [x] `make setup` succeeds from a clean supported local environment.
- [x] Final post-hardening `make check` passes: Ruff, Prettier, ESLint, strict mypy,
  TypeScript, 29 backend tests, 10 frontend tests, Vite production build, and
  dependency audits.
- [x] `pip-audit` reports no known vulnerabilities in the Python production lock;
  npm production audit reports zero vulnerabilities.
- [x] Standalone `docker compose --env-file .env.example config --quiet` validates
  the Compose contract.
- [x] The Compose startup path used by `make dev` starts healthy `db`, `api`, and
  `web` services (verified with its detached `docker compose up --build -d`
  equivalent).
- [x] `make migrate` applies the baseline migration to live local PostgreSQL.
- [x] Alembic reports the expected head and generates offline migration SQL.
- [x] Final post-hardening `GET /health` contract passes through the system API tests
  and local smoke-server readiness check.
- [x] Final post-hardening GraphQL POST for `health` and `appInfo` passes through the
  system API tests and the Vite proxy smoke path.
- [x] Frontend format, ESLint (zero warnings), type check, 4-file/10-test Vitest
  suite, and production build pass; the tests cover Apollo foundation loading,
  online metadata, the offline state, and presence of its retry control.
- [x] `make smoke` starts API/Vite, POSTs `health`/`appInfo` through the
  browser-facing same-origin `/graphql` proxy, validates it, and cleans up.
- [x] API development/production and web development container images build.
- [x] `make stop` stops Compose services without deleting the database volume; the
  retained volume was inspected before a successful healthy restart.
- [x] CI is exercised on the default branch.

Docker Desktop for Apple silicon was used to build all configured image targets,
start the complete healthy stack, migrate live PostgreSQL, stop without deleting the
named volume, and restart successfully. GitHub Actions subsequently passed all
configured jobs on the default branch. `make smoke` is the direct non-visual
acceptance for web-to-API connectivity; it does not claim manual browser layout
verification.

### Phase 0 acceptance

```text
make env
make setup
make check
make smoke
make dev

# in another terminal
make migrate
curl http://localhost:8000/health
curl -H 'content-type: application/json' \
  --data '{"query":"query { health appInfo { name version environment } }"}' \
  http://localhost:8000/graphql

make stop
```

Expected result: API health contracts pass; the web uses its same-origin Vite proxy
to show live API foundation status; the financial dashboard remains explicitly
synthetic; and shutdown preserves the PostgreSQL named volume. No finance or AI
feature is represented as real.

## Phase 1 — deterministic financial ledger

- [x] Define the first vertical slice and its acceptance semantics in
  `docs/phase1-ledger.md`.
- [x] Implement user profile and development-auth ownership seam.
- [x] Add merchant and hierarchical system/user category models.
- [x] Add transaction model using `Decimal`/`NUMERIC`, currency, type, and status.
- [x] Add people, receivables, payables, and immutable settlement history.
- [x] Add manually managed recurring payments.
- [x] Enforce same-user relationships, amount/currency checks, and foreign keys.
- [x] Add query-driven composite indexes.
- [x] Implement repositories and small transaction-bound services.
- [x] Implement deterministic financial-summary semantics per currency.
- [x] Add keyset-paginated GraphQL queries and typed manual mutations.
- [x] Keep resolvers free of SQL and financial calculations.
- [x] Inspect relationship loading; explicit aggregate/projection queries avoid an
  N+1 path, so no DataLoader is introduced.
- [x] Replace placeholder dashboard values with live GraphQL data.
- [x] Add tested frontend controls for transactions, people, obligations,
  settlements, and recurring payments.
- [x] Add unit tests for money, statuses, periods/timezones, and summaries.
- [x] Add repository/GraphQL integration and cross-user authorization tests.
- [x] Seed a realistic, idempotent development INR ledger.
- [x] Bootstrap a fresh Compose database through migrations and seed before API
  startup.

Acceptance: a user can manage manual transactions and obligations; totals are exact,
tenant-isolated, tested, and visible in the dashboard.

### Phase 1 verification

- [x] Alembic upgrade, downgrade, and re-upgrade pass against PostgreSQL.
- [x] The PostgreSQL-enabled backend suite passes: 99 tests.
- [x] Ruff and strict mypy pass.
- [x] Frontend ESLint, Prettier, TypeScript, 30 tests, and production build pass.
- [x] Compose configuration validates.
- [x] A separate empty Compose volume migrates and seeds successfully; the second
  seed is a no-op.
- [x] Phase 1 implementation commit `15abd32` passed every job in GitHub Actions
  run `30081162989`: backend, frontend, proxy smoke, container contracts, and secret
  scan.

## Phase 2 — unified ingestion and provenance

- [x] Define the ingestion, replay, provenance, connector, AI handoff, and Google
  source acceptance semantics in `docs/phase2-ingestion.md`.
- [x] Add `SourceConnection`, immutable-source-field `RawEvent`, separate processing
  state, and owner-safe `Evidence`.
- [x] Define a persisted, versioned normalized financial-event contract.
- [x] Define connector fetch/normalize/health interface and explicit registry.
- [ ] Implement manual, CSV, and mock receipt connectors only.
- [x] Enforce external identity/content-hash idempotency with unique constraints.
- [x] Add explicit processing-state transitions and retry semantics.
- [x] Persist provenance through one atomic canonical-ledger handoff.
- [x] Test duplicate delivery, concurrent ingestion, failure resume, and ownership.

Acceptance: one mock event flows through raw storage and normalization to one
canonical record with evidence, and replay does not duplicate it.

## Phase 3 — natural-language notes

- [ ] Add provider-neutral structured-completion interface and mock adapter.
- [ ] Version extraction prompts outside business services.
- [ ] Add discriminated Pydantic schemas for supported event types.
- [ ] Resolve relative dates from source timestamp and user timezone.
- [ ] Add configurable, calibrated confidence policy.
- [ ] Add proposed-event persistence and review queue.
- [ ] Add one real provider adapter behind server-only configuration.
- [ ] Record safe model/prompt/schema/latency/token/cost metadata.
- [ ] Add adversarial prompt-injection, invalid-output, timeout, and retry tests.
- [ ] Create labelled extraction evaluation dataset and evaluator.

Acceptance: “Lent Rahul ₹2,000 yesterday” creates a traceable proposal; missing facts
remain unknown; uncertain results require confirmation.

## Phase 4 — reconciliation

- [ ] Implement exact-identity and candidate lookup.
- [ ] Implement configurable explainable scoring signals.
- [ ] Return `merge`, `possible_duplicate`, or `new_transaction` with reasons.
- [ ] Preserve all evidence after a canonical merge.
- [ ] Add review flow and safe merge/unmerge audit behavior.
- [ ] Build labelled duplicate/non-duplicate dataset.
- [ ] Measure precision, recall, F1, and false-merge slices.

Acceptance: repeated representations do not inflate spending; ambiguous cases are not
silently merged.

## Phase 5 — categorization and correction memory

- [ ] Apply user rule → merchant map → verified correction → retrieval → model order.
- [ ] Store classifier source, version, confidence, and override.
- [ ] Add `UserCorrection` audit history.
- [ ] Ensure corrections affect subsequent deterministic matching.
- [ ] Establish non-vector retrieval baseline.
- [ ] Add pgvector only if ADR-006 evaluation criterion is met.
- [ ] Evaluate accuracy/macro F1 and per-category errors.

## Phase 6 — deterministic analytics and insights

- [ ] Spending by category, merchant, and period.
- [ ] Contribution analysis for total, count, and average-size changes.
- [ ] Conservative recurring-payment detector requiring repeated observations.
- [ ] Deterministic large-transaction, trend, forgotten-debt, and concentration rules.
- [ ] Ground every insight in supporting record IDs and computed data.
- [ ] Unit-test period boundaries, zero baselines, refunds, and currencies.

Acceptance: “Why did spending change?” has a complete structured answer before an LLM
summarizes it.

## Phase 7 — read-only finance agent

- [ ] Define narrow typed tools over existing services.
- [ ] Inject user identity server-side and re-authorize inside every tool.
- [ ] Implement intent/router, allowlist, execution limits, and result verifier.
- [ ] Keep SQL, arbitrary network access, and write tools unavailable.
- [ ] Add deterministic fallback when the provider is unavailable.
- [ ] Adopt LangGraph only if state-machine complexity justifies it.
- [ ] Evaluate tool choice, numerical correctness, grounding, unsupported claims,
  latency, cost, prompt injection, and cross-tenant attempts.

## Phase 8 — real external connector

- [ ] Complete provider data inventory and retention review.
- [ ] Use official OAuth/API with least scopes, state, PKCE, and exact callbacks.
- [ ] Encrypt tokens with managed keys; implement disconnect/revocation.
- [ ] Filter financial relevance before model calls.
- [ ] Store minimum content and bounded provenance.
- [ ] Add contract fixtures, rate-limit/retry tests, and sync observability.

## Phase 9 — asynchronous and real-time UX

- [ ] Measure the need for durable independent work.
- [ ] Implement transactional job/outbox or justified queue.
- [ ] Add bounded retries, jitter, dead-letter/review behavior, and backpressure.
- [ ] Make every worker handler tenant-aware and idempotent.
- [ ] Expose processing state through polling, subscription, or WebSocket based on
  measured UX need.

## Phase 10 — observability and deployment

- [ ] Production images and environment configuration.
- [ ] Managed PostgreSQL, backups, and tested restore.
- [ ] TLS, production auth, rate limits, and GraphQL cost controls.
- [ ] Request/job correlation IDs and structured redacted logs.
- [ ] OpenTelemetry-compatible traces and service-level metrics.
- [ ] AI quality/latency/token/cost and connector lag dashboards.
- [ ] Migration, rollback, incident, deletion, and token-rotation runbooks.
- [ ] Deployment smoke tests and post-deploy verification.

## Explicitly deferred without evidence

- [ ] Kafka
- [ ] Kubernetes
- [ ] Microservice decomposition
- [ ] MongoDB
- [ ] Neo4j
- [ ] Elasticsearch
- [ ] Dedicated vector database
- [ ] Write-capable financial agent

Checking any item above requires a measured bottleneck/use case, security and
operational analysis, and a new or superseding ADR.
