"""Replay-safe source-to-ledger orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.connectors.contracts import (
    Connector,
    ConnectorEnvelope,
    ConnectorHealthStatus,
)
from app.db.session import Database
from app.domain.enums import (
    NormalizedEventKind,
    RawEventState,
    SourceConnectionStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.domain.normalization import normalize_display_text
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.dto import (
    ConnectorSyncResult,
    IngestionResult,
    SourceConnectionView,
    StoredRawEvent,
)
from app.ingestion.errors import (
    ConnectorContentError,
    ConnectorUnavailableError,
    IngestionConflictError,
)
from app.ingestion.identity import canonical_envelope, content_sha256, event_identity_key
from app.ingestion.repository import IngestionRepository, normalized_model_confidence
from app.ingestion.state import require_state_transition
from app.ledger.commands import parse_create_transaction
from app.ledger.errors import LedgerError, LedgerNotFoundError
from app.ledger.repository import LedgerRepository
from app.models import NormalizedFinancialEvent, RawEventProcessing

NORMALIZER_VERSION = "1"
_POSTABLE_KINDS: dict[NormalizedEventKind, TransactionType] = {
    NormalizedEventKind.EXPENSE: TransactionType.EXPENSE,
    NormalizedEventKind.INCOME: TransactionType.INCOME,
    NormalizedEventKind.TRANSFER: TransactionType.TRANSFER,
    NormalizedEventKind.REFUND: TransactionType.REFUND,
    NormalizedEventKind.SHARED_EXPENSE: TransactionType.SHARED_EXPENSE,
}
_TERMINAL_STATES = frozenset(
    {
        RawEventState.PROCESSED,
        RawEventState.NEEDS_REVIEW,
    }
)


class IngestionService:
    """Durably ingest connector pages without duplicate canonical writes."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def sync_connector(
        self,
        user_id: UUID,
        connector: Connector,
        *,
        connection_key: str = "default",
    ) -> ConnectorSyncResult:
        """Fetch one connector page, durably process it, then advance its cursor."""
        connection = await self._ensure_connection(
            user_id,
            connector,
            connection_key=connection_key,
        )
        health = await connector.health()
        if health.status is not ConnectorHealthStatus.HEALTHY:
            raise ConnectorUnavailableError(
                code=health.code or "CONNECTOR_UNAVAILABLE",
                message="The source connector is not currently available.",
            )

        batch = await connector.fetch(dict(connection.cursor))
        results: list[IngestionResult] = []
        for envelope in batch.events:
            results.append(
                await self._ingest_for_connection(
                    user_id,
                    connection,
                    connector,
                    envelope,
                )
            )
        async with self._database.session_factory()() as session, session.begin():
            await IngestionRepository(session).update_connection_cursor(
                user_id,
                connection.id,
                batch.next_cursor,
                synced_at=datetime.now(UTC),
            )
        return ConnectorSyncResult(connection_id=connection.id, events=tuple(results))

    async def ingest_envelope(
        self,
        user_id: UUID,
        connector: Connector,
        envelope: ConnectorEnvelope,
        *,
        connection_key: str = "default",
    ) -> IngestionResult:
        """Ingest one envelope directly, primarily for push/import adapters."""
        connection = await self._ensure_connection(
            user_id,
            connector,
            connection_key=connection_key,
        )
        return await self._ingest_for_connection(
            user_id,
            connection,
            connector,
            envelope,
        )

    async def _ensure_connection(
        self,
        user_id: UUID,
        connector: Connector,
        *,
        connection_key: str,
    ) -> SourceConnectionView:
        normalized_key = normalize_display_text(connection_key)
        if not normalized_key or len(normalized_key) > 128:
            raise IngestionConflictError(
                code="INVALID_CONNECTION_KEY",
                message="The source connection key is invalid.",
            )
        async with self._database.session_factory()() as session, session.begin():
            ledger = LedgerRepository(session)
            if await ledger.get_user(user_id) is None:
                raise LedgerNotFoundError(
                    code="PROFILE_NOT_FOUND",
                    message="The ledger profile was not found.",
                )
            connection = await IngestionRepository(session).ensure_connection(
                user_id,
                connector.descriptor,
                connection_key=normalized_key,
            )
            if connection.status is not SourceConnectionStatus.ACTIVE:
                raise IngestionConflictError(
                    code="SOURCE_CONNECTION_INACTIVE",
                    message="The source connection is not active.",
                )
            return connection

    async def _ingest_for_connection(
        self,
        user_id: UUID,
        connection: SourceConnectionView,
        connector: Connector,
        envelope: ConnectorEnvelope,
    ) -> IngestionResult:
        stored = await self._store_raw_event(
            user_id,
            connection,
            envelope,
        )
        terminal = await self._terminal_result(user_id, stored)
        if terminal is not None:
            return terminal

        try:
            normalized = connector.normalize(envelope)
        except ConnectorContentError as exc:
            return await self._mark_failed(user_id, stored, exc.code)

        return await self._process_normalized(
            user_id,
            connection,
            envelope,
            stored,
            normalized,
        )

    async def _store_raw_event(
        self,
        user_id: UUID,
        connection: SourceConnectionView,
        envelope: ConnectorEnvelope,
    ) -> StoredRawEvent:
        serialized = canonical_envelope(envelope)
        content_hash = content_sha256(envelope)
        identity_key = event_identity_key(envelope, content_hash=content_hash)
        payload = serialized.get("payload")
        if not isinstance(payload, dict):
            raise ConnectorContentError(
                code="INVALID_SOURCE_PAYLOAD",
                message="The source event payload must be a JSON object.",
            )
        async with self._database.session_factory()() as session, session.begin():
            return await IngestionRepository(session).store_raw_event(
                user_id,
                connection.id,
                envelope,
                identity_key=identity_key,
                content_hash=content_hash,
                payload=payload,
            )

    async def _terminal_result(
        self,
        user_id: UUID,
        stored: StoredRawEvent,
    ) -> IngestionResult | None:
        async with self._database.session_factory()() as session:
            repository = IngestionRepository(session)
            processing = await repository.get_processing(user_id, stored.id)
            if processing.state not in _TERMINAL_STATES:
                return None
            normalized = await repository.normalized_for_raw_event(user_id, stored.id)
            evidence = await repository.evidence_for_raw_event(user_id, stored.id)
            return IngestionResult(
                raw_event_id=stored.id,
                normalized_event_id=normalized.id if normalized is not None else None,
                transaction_id=evidence.transaction_id if evidence is not None else None,
                state=processing.state,
                replayed=not stored.created,
                error_code=processing.last_error_code,
            )

    async def _mark_failed(
        self,
        user_id: UUID,
        stored: StoredRawEvent,
        error_code: str,
    ) -> IngestionResult:
        async with self._database.session_factory()() as session, session.begin():
            repository = IngestionRepository(session)
            processing = await repository.get_processing(
                user_id,
                stored.id,
                for_update=True,
            )
            if processing.state in _TERMINAL_STATES:
                normalized = await repository.normalized_for_raw_event(user_id, stored.id)
                evidence = await repository.evidence_for_raw_event(user_id, stored.id)
                return IngestionResult(
                    raw_event_id=stored.id,
                    normalized_event_id=normalized.id if normalized is not None else None,
                    transaction_id=evidence.transaction_id if evidence is not None else None,
                    state=processing.state,
                    replayed=not stored.created,
                    error_code=processing.last_error_code,
                )
            require_state_transition(processing.state, RawEventState.FAILED)
            processing.state = RawEventState.FAILED
            processing.attempt_count += 1
            processing.last_error_code = error_code
        return IngestionResult(
            raw_event_id=stored.id,
            normalized_event_id=None,
            transaction_id=None,
            state=RawEventState.FAILED,
            replayed=not stored.created,
            error_code=error_code,
        )

    async def _process_normalized(
        self,
        user_id: UUID,
        connection: SourceConnectionView,
        envelope: ConnectorEnvelope,
        stored: StoredRawEvent,
        normalized: NormalizedFinancialEventV1,
    ) -> IngestionResult:
        async with self._database.session_factory()() as session, session.begin():
            repository = IngestionRepository(session)
            ledger = LedgerRepository(session)
            processing = await repository.get_processing(
                user_id,
                stored.id,
                for_update=True,
            )
            if processing.state in _TERMINAL_STATES:
                existing = await repository.normalized_for_raw_event(user_id, stored.id)
                evidence = await repository.evidence_for_raw_event(user_id, stored.id)
                return IngestionResult(
                    raw_event_id=stored.id,
                    normalized_event_id=existing.id if existing is not None else None,
                    transaction_id=evidence.transaction_id if evidence is not None else None,
                    state=processing.state,
                    replayed=not stored.created,
                    error_code=processing.last_error_code,
                )

            processing.attempt_count += 1
            persisted = await repository.store_normalized_event(
                user_id,
                stored.id,
                normalized,
                normalizer_key=connection.connector_type.value,
                normalizer_version=NORMALIZER_VERSION,
            )
            if processing.state is not RawEventState.NORMALIZED:
                require_state_transition(processing.state, RawEventState.NORMALIZED)
                processing.state = RawEventState.NORMALIZED
            processing.last_error_code = None

            result = await self._post_or_queue_review(
                user_id,
                envelope,
                repository,
                ledger,
                processing,
                persisted,
            )
            return IngestionResult(
                raw_event_id=stored.id,
                normalized_event_id=persisted.id,
                transaction_id=result,
                state=processing.state,
                replayed=not stored.created,
                error_code=processing.last_error_code,
            )

    async def _post_or_queue_review(
        self,
        user_id: UUID,
        envelope: ConnectorEnvelope,
        repository: IngestionRepository,
        ledger: LedgerRepository,
        processing: RawEventProcessing,
        event: NormalizedFinancialEvent,
    ) -> UUID | None:
        transaction_type = _POSTABLE_KINDS.get(event.event_kind)
        if (
            transaction_type is None
            or event.amount is None
            or event.currency is None
            or event.occurred_at is None
        ):
            require_state_transition(processing.state, RawEventState.NEEDS_REVIEW)
            processing.state = RawEventState.NEEDS_REVIEW
            processing.last_error_code = "REVIEW_REQUIRED"
            return None

        category_id = None
        if event.category_hint is not None:
            category_id = await ledger.find_visible_category_id(
                user_id,
                normalize_display_text(event.category_hint).casefold(),
            )
        try:
            command = parse_create_transaction(
                amount=format(event.amount, "f"),
                currency=event.currency,
                transaction_type=transaction_type,
                description=event.description,
                transaction_date=event.occurred_at,
                status=TransactionStatus.POSTED,
                category_id=category_id,
                merchant_name=event.merchant_name,
                source=TransactionSource.INGESTION,
                confidence=normalized_model_confidence(event),
            )
        except LedgerError:
            require_state_transition(processing.state, RawEventState.NEEDS_REVIEW)
            processing.state = RawEventState.NEEDS_REVIEW
            processing.last_error_code = "LEDGER_VALIDATION_REVIEW"
            return None

        transaction = await ledger.create_transaction(user_id, command)
        await repository.add_evidence(
            user_id,
            processing.raw_event_id,
            event.id,
            transaction.id,
            locator=dict(envelope.locator),
            excerpt=envelope.evidence_excerpt,
        )
        require_state_transition(processing.state, RawEventState.PROCESSED)
        processing.state = RawEventState.PROCESSED
        processing.last_error_code = None
        return transaction.id
