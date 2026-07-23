# ADR-006: Add pgvector only when retrieval is justified

- **Status:** Accepted
- **Date:** 2026-07-23
- **Implementation:** Deferred; Phase 0 does not enable pgvector or create embeddings.

## Context

Semantic similarity may help find a user's previous category corrections, equivalent
merchant descriptions, or relevant verified history. It is not needed for exact
amount/date filters, ownership, obligations, or totals. Premature embeddings add
model cost, privacy/retention obligations, index tuning, and another source of
nondeterministic behavior.

## Decision

Keep exact financial queries in relational SQL. Add pgvector inside PostgreSQL only
when a versioned evaluation demonstrates that semantic retrieval materially improves
quality or model cost over deterministic rules, merchant mappings, text search, and
indexed relational lookup.

Candidate retrieval must be tenant-scoped and use verified records. Embeddings are
derived sensitive data and follow source deletion and retention policy.

## Alternatives

- **Enable pgvector from the start:** simplifies later experimentation but creates
  unused schema and operational/privacy work now.
- **Dedicated vector database:** may scale specialized retrieval but adds another
  datastore and consistency boundary before a measured need.
- **Never use semantic retrieval:** simplest, but may leave value on the table when
  descriptions and corrections are linguistically varied.

## Consequences

- MVP architecture and financial queries remain simple and exact.
- A retrieval dataset, baseline, quality metric, latency, and cost comparison are
  prerequisites to adoption.
- pgvector can share PostgreSQL ownership and backup boundaries if selected.
- Vector search never becomes the source for financial totals.
- Embedding model/version changes require re-indexing and evaluation planning.
