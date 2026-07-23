# ADR-001: PostgreSQL over MongoDB

- **Status:** Accepted
- **Date:** 2026-07-23
- **Implementation:** PostgreSQL development infrastructure is part of Phase 0;
  financial tables begin in Phase 1.

## Context

SpendGraph AI links transactions, users, people, obligations, settlements,
categories, merchants, source events, and evidence. Financial correctness requires
atomic state changes, uniqueness, ownership-aware relationships, decimal arithmetic,
and predictable analytical queries. Some raw provider payloads are semi-structured.

## Decision

Use PostgreSQL as the system of record. Represent the personal financial graph with
relational tables, foreign keys, check/unique constraints, transactions, and
query-driven indexes. Store bounded source payloads in `JSONB` when their shape
legitimately varies. Use `NUMERIC` for money.

## Alternatives

- **MongoDB:** flexible documents fit changing provider payloads, but core ledger
  relationships and invariants would need more application enforcement. PostgreSQL
  already provides `JSONB` at the edge without giving up relational integrity.
- **Neo4j:** native traversal is attractive in name, but MVP queries are shallow
  ownership, aggregation, and relationship joins. A second consistency and
  operational model is not justified.
- **Multiple datastores:** could specialize workloads but introduces synchronization,
  backup, observability, and deletion complexity before measured need.

## Consequences

- Ledger writes can be atomic and database constraints can defend invariants.
- SQL supports deterministic summaries and mature query-plan tooling.
- The team must design migrations and indexes carefully.
- Some connector payloads require normalization rather than becoming arbitrary
  documents.
- Deep graph traversal or analytical scale may require later reevaluation, based on
  measured workloads rather than product naming.
