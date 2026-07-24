# ADR-004: Normalize every connector behind one contract

- **Status:** Accepted
- **Date:** 2026-07-23
- **Implementation:** Phase 2 contract, registry, raw-event pipeline, mock/manual/CSV
  adapters, fixture-tested Gmail adapter, and Google Keep Takeout import are
  implemented. Production Gmail OAuth remains Phase 8.

## Context

Manual notes, CSV files, receipt emails, and future provider APIs use different
authentication, cursors, payloads, identifiers, and failure behavior. Allowing these
details into ledger, reconciliation, or AI code would multiply conditionals and make
adding connectors unsafe.

## Decision

Each connector owns provider-specific fetch, cursor, health, and envelope
normalization behavior. It emits a common, versioned normalized financial-event
contract. Shared ingestion then owns immutable raw-event storage, idempotency,
interpretation, validation, processing state, and handoff to reconciliation/ledger
services.

Provider payload and provenance remain available through a bounded raw/evidence
record; normalization is not evidence destruction.

## Alternatives

- **Provider-specific pipelines:** faster for the first connector but duplicate
  retry, validation, observability, and ledger logic.
- **One universal connector with conditionals:** centralizes code while creating a
  high-coupling module that is difficult to test and deploy safely.
- **Normalize only after AI extraction:** makes model prompts and business logic
  provider-aware and increases cost and attack surface.

## Consequences

- New connectors can be contract-tested without changing domain services.
- Provider quirks stop at an adapter boundary.
- The normalized contract requires versioning and compatibility discipline.
- Not every source field has a canonical equivalent; evidence and metadata must
  preserve useful context.
- Connectors still require individual OAuth, rate-limit, privacy, and retention
  reviews.
