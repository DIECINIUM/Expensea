# ADR-002: GraphQL for the product API

- **Status:** Accepted
- **Date:** 2026-07-23
- **Implementation:** Phase 0 uses Apollo to execute a same-origin
  `health`/`appInfo` query through the Vite proxy and displays the API foundation
  state. Financial schema fields are planned.

## Context

The web application will compose transactions, summaries, people, obligations,
recurring payments, evidence, insights, and review items in several screen-specific
shapes. The frontend benefits from a discoverable typed contract and generated
TypeScript types.

## Decision

Use Strawberry GraphQL on FastAPI for the product API and Apollo Client in the React
application. Keep resolvers as delivery adapters: they validate boundary input,
obtain authenticated context, call services/use cases, and map typed results.
Repositories own persistence queries.

Retain narrow REST endpoints where protocol or operations make them clearer, such as
health checks and potentially OAuth callbacks.

## Alternatives

- **REST only:** simple and familiar, but dashboard composition can lead to many
  endpoints, over/under-fetching, or bespoke aggregate resources.
- **tRPC:** strong TypeScript ergonomics, but the backend is Python and Strawberry
  provides a language-neutral schema.
- **Direct database access from the client:** rejected because it bypasses the
  authorization, business-rule, and audit boundaries.

## Consequences

- Client operations can request the shape they need and use generated types.
- The development client can use a same-origin path and proxy rather than embedding
  an API origin in browser code.
- A local/CI smoke contract verifies the browser-facing proxy path without depending
  on synthetic dashboard values.
- The schema becomes a versioned product contract.
- N+1 queries, unbounded lists, aliases/fragments, and expensive query shapes require
  pagination, DataLoader, query-cost limits, timeouts, and monitoring.
- Field-level convenience must not fragment financial semantics; central services
  still define totals and authorization.
- GraphQL errors must remain stable and non-sensitive.
- Query execution over GET is disabled; operations use POST.
