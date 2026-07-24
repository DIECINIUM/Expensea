# Phase 2 ingestion and provenance

**Status:** implementation acceptance contract

**Started:** 2026-07-24

## Goal

Phase 2 introduces a replay-safe boundary between external financial sources and the
canonical ledger. A connector may deliver the same event more than once, fail midway,
or provide hostile content. SpendGraph must preserve a bounded source record, normalize
it behind a versioned contract, and create at most one canonical record with traceable
evidence.

This phase also establishes the source boundary needed by the next natural-language
extraction slice. Model output is always an untrusted proposal and cannot bypass the
deterministic ledger service.

## Supported first sources

| Source | First supported path | Notes |
| --- | --- | --- |
| Manual financial note | Authenticated application input | Becomes an immutable raw event before interpretation. |
| Mock receipt | Deterministic connector fixture | Proves replay and provenance without an external dependency. |
| Gmail receipts | Official Gmail API with read-only authorization | Fetch only likely financial messages and retain minimized content. OAuth credentials are deployment configuration, never repository data. |
| Google Keep notes | User-provided Google Takeout export | Consumer Keep does not expose the same general-purpose OAuth path as Gmail. Managed Workspace Keep API support can be a later adapter. |
| Google Play subscriptions | Gmail receipt and renewal evidence | The Android Publisher API is package- and purchase-token-oriented, not a consumer-wide subscription feed. |

No source is scraped. Access tokens, refresh tokens, cookies, full mailbox dumps, and
unnecessary attachments are not persisted in ingestion metadata.

## Persistence invariants

- Every private ingestion row carries `user_id`.
- Child records use ownership-aware foreign keys where a private parent is referenced.
- A source connection has one opaque, non-secret connection key per user and connector.
- A raw event has one deterministic identity per connection:
  `external:<provider-id>` when a stable provider ID exists, otherwise
  `sha256:<content-hash>`.
- Raw event source fields and minimized payload are insert-only application data.
  Processing state lives on the normalized record.
- One raw event and normalizer version produce at most one normalized event.
- One accepted normalized event produces at most one canonical transaction.
- Evidence and its canonical transaction commit in the same database transaction.
- Amounts use `Decimal`/`NUMERIC`; currencies remain explicit; timestamps are
  timezone-aware.

## Connector contract

A connector exposes stable metadata plus three bounded operations:

1. `health()` reports whether configuration is usable without returning secrets.
2. `fetch(cursor)` returns provider envelopes and a resumable cursor.
3. `normalize(envelope)` returns a versioned, provider-neutral financial event.

Provider envelopes are data, never instructions. Normalization does not perform ledger
writes. Connectors are registered by a stable key so another application can be added
without changing the ingestion service.

## State transitions

```text
received -> normalized -> processed
                    \-> needs_review
received/normalized -> failed -> normalized (explicit retry)
```

Only declared transitions are allowed. Failures retain a non-sensitive error code and
attempt count, not arbitrary exception text or source content.

## First vertical-slice acceptance

Given one mock receipt envelope:

1. ingestion stores one bounded raw event;
2. normalization stores one versioned financial event;
3. deterministic validation creates one canonical transaction;
4. one evidence record links the transaction to the raw event; and
5. replaying the same envelope returns the existing result without another raw event,
   normalized event, transaction, or evidence row.

The slice must also prove:

- a second user cannot read or attach another user's source records;
- content-hash identity works when an external ID is absent;
- malformed amounts, currencies, timestamps, and transitions fail before a ledger
  write;
- a failed interpretation leaves the raw event available for retry; and
- logs and GraphQL errors do not expose minimized payload content.

## AI handoff policy

Natural-language and email interpretation uses a provider-neutral structured completion
port. The initial real adapter targets an Ollama-compatible `/api/chat` endpoint through
server-only settings. It sends bounded source text, asks for a strict JSON schema, and
discards any model reasoning trace.

Provider timeouts, malformed output, unknown required facts, or low confidence produce a
reviewable/failed proposal. They never create a posted transaction automatically.
Tests use a deterministic mock provider; a live-provider contract test is opt-in.

## Google authorization boundary

Real Gmail sync requires a Google OAuth client, consent screen, redirect URI, and the
minimum suitable read-only scope. Those values and authorized tokens belong in a secure
deployment secret/token store. Until encrypted token storage and disconnect/revocation
are implemented, the connector accepts only an ephemeral authorized client supplied by
the runtime and cannot persist credentials.

Google Keep consumer notes enter through an explicit Takeout import. The import accepts
only supported note JSON fields, ignores attachments by default, bounds text size, and
maps Keep labels to untrusted tag suggestions.

## Out of scope for this slice

- automatic reconciliation or silent duplicate merges beyond source identity;
- autonomous write-capable agents;
- arbitrary mailbox search or retention of entire messages;
- browser scraping of Google services;
- exchange-rate conversion;
- direct consumer-wide Google Play subscription access; and
- background broker infrastructure before runtime evidence justifies it.
