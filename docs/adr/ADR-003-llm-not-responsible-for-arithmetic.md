# ADR-003: LLMs are not responsible for financial arithmetic

- **Status:** Accepted
- **Date:** 2026-07-23
- **Implementation:** Architectural constraint. AI integration is not implemented in
  Phase 0.

## Context

Language models are useful for interpreting unstructured notes and explaining
results, but financial totals and state transitions require exactness,
repeatability, authorization, and auditability. A plausible natural-language answer
can conceal an omitted transaction or arithmetic error.

## Decision

LLMs may produce schema-constrained extraction/classification proposals, select
allowlisted read-only tools, and explain deterministic results. Python `Decimal`,
SQL `NUMERIC`, database constraints, and deterministic services exclusively own:

- arithmetic and aggregation;
- balances and financial-summary semantics;
- currency rules;
- authorization;
- reconciliation decisions that mutate canonical state; and
- ledger state transitions.

Numerical statements in generated explanations must be grounded in tool/service
output.

## Alternatives

- **Ask the LLM to calculate from a transaction list:** easy to prototype but
  nondeterministic, difficult to audit, costly, and vulnerable to truncation or
  prompt injection.
- **Let an agent execute arbitrary SQL:** flexible but creates unacceptable tenant,
  integrity, and exfiltration risk.
- **Avoid AI entirely:** would preserve determinism but make ambiguous natural
  language and flexible explanation substantially less useful.

## Consequences

- The product remains useful and correct when an AI provider is unavailable.
- Deterministic services require explicit, well-tested financial semantics.
- AI answers may be less free-form because they are bounded by retrieved facts.
- Extraction proposals need validation, confidence policy, provenance, and review.
- Evaluation can separate interpretation quality from numerical correctness.
