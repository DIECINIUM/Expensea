# ADR-005: PostgreSQL before a dedicated event broker

- **Status:** Accepted
- **Date:** 2026-07-23
- **Implementation:** Phase 0 configures a modular API and PostgreSQL/Alembic
  foundation. The Docker-backed runtime was not started in the verification
  environment; durable background processing is deferred.

## Context

Connector sync and AI extraction can become slow, bursty, and retryable. A broker can
isolate that work, but an MVP has low event volume, one owning application, and no
demonstrated need for many independent consumers or event replay.

## Decision

Begin with the FastAPI modular monolith and PostgreSQL. Use direct synchronous work
for short operations. Introduce an application job abstraction and, when durability
is needed, a PostgreSQL-backed job/outbox before adopting separate broker
infrastructure.

Adopt Redis plus a worker framework when latency isolation, concurrency,
backpressure, process-independent work, or durable retries are measured needs.
Consider Kafka only for sustained high throughput, replay, partition ordering, and
multiple independent consumer groups.

## Alternatives

- **Kafka immediately:** powerful replay and consumer model, with significant local
  and production operational burden not justified by MVP traffic.
- **Redis queue immediately:** simpler than Kafka but still another stateful
  dependency before slow work exists.
- **Only in-process background tasks indefinitely:** minimal setup but work can be
  lost on restart and does not coordinate cleanly across API replicas.

## Consequences

- Phase 0 is easier to run, reason about, and test.
- Database transactions can atomically persist state and an outbox/job intent.
- Worker-facing service boundaries and idempotent handlers must be designed early
  enough to avoid coupling to request lifetimes.
- PostgreSQL is not treated as an unlimited queue; queue depth, latency, retries, and
  database load determine when to graduate.
- Broker adoption has explicit operational evidence and an ADR update.
