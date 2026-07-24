"""Owner-scoped persistence operations for replay-safe ingestion."""

from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.contracts import ConnectorDescriptor, ConnectorEnvelope
from app.domain.enums import EvidenceKind, RawEventState
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.dto import SourceConnectionView, StoredRawEvent
from app.ingestion.errors import IngestionConflictError
from app.models import (
    Evidence,
    NormalizedFinancialEvent,
    RawEvent,
    RawEventProcessing,
    SourceConnection,
)


class IngestionRepository:
    """Database adapter requiring owner identity on every private operation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_connection(
        self,
        user_id: UUID,
        descriptor: ConnectorDescriptor,
        *,
        connection_key: str,
    ) -> SourceConnectionView:
        connection_id = uuid4()
        statement = (
            pg_insert(SourceConnection)
            .values(
                id=connection_id,
                user_id=user_id,
                connector_type=descriptor.key,
                connection_key=connection_key,
                display_name=descriptor.display_name,
                configuration={},
                cursor={},
            )
            .on_conflict_do_nothing(
                constraint="uq_source_connections_user_connector_key",
            )
            .returning(SourceConnection.id)
        )
        inserted_id = (await self._session.execute(statement)).scalar_one_or_none()
        selected_id = inserted_id or await self._session.scalar(
            select(SourceConnection.id).where(
                SourceConnection.user_id == user_id,
                SourceConnection.connector_type == descriptor.key,
                SourceConnection.connection_key == connection_key,
            )
        )
        if selected_id is None:
            msg = "Connection upsert did not return an owner-visible row"
            raise RuntimeError(msg)
        return await self.get_connection(user_id, selected_id)

    async def get_connection(
        self,
        user_id: UUID,
        connection_id: UUID,
    ) -> SourceConnectionView:
        connection = await self._session.scalar(
            select(SourceConnection).where(
                SourceConnection.id == connection_id,
                SourceConnection.user_id == user_id,
            )
        )
        if connection is None:
            raise IngestionConflictError(
                code="SOURCE_CONNECTION_NOT_FOUND",
                message="The source connection was not found.",
            )
        return SourceConnectionView(
            id=connection.id,
            connector_type=connection.connector_type,
            connection_key=connection.connection_key,
            display_name=connection.display_name,
            status=connection.status,
            cursor=dict(connection.cursor),
        )

    async def store_raw_event(
        self,
        user_id: UUID,
        connection_id: UUID,
        envelope: ConnectorEnvelope,
        *,
        identity_key: str,
        content_hash: str,
        payload: dict[str, Any],
    ) -> StoredRawEvent:
        raw_event_id = uuid4()
        statement = (
            pg_insert(RawEvent)
            .values(
                id=raw_event_id,
                user_id=user_id,
                source_connection_id=connection_id,
                identity_key=identity_key,
                external_event_id=envelope.external_event_id,
                content_sha256=content_hash,
                source_event_type=envelope.event_type,
                occurred_at=envelope.occurred_at,
                payload=payload,
            )
            .on_conflict_do_nothing(
                constraint="uq_raw_events_connection_identity",
            )
            .returning(RawEvent.id)
        )
        inserted_id = (await self._session.execute(statement)).scalar_one_or_none()
        selected_id = inserted_id or await self._session.scalar(
            select(RawEvent.id).where(
                RawEvent.user_id == user_id,
                RawEvent.source_connection_id == connection_id,
                RawEvent.identity_key == identity_key,
            )
        )
        if selected_id is None:
            msg = "Raw-event upsert did not return an owner-visible row"
            raise RuntimeError(msg)

        existing_hash = await self._session.scalar(
            select(RawEvent.content_sha256).where(
                RawEvent.id == selected_id,
                RawEvent.user_id == user_id,
            )
        )
        if existing_hash != content_hash:
            raise IngestionConflictError(
                code="SOURCE_IDENTITY_CONTENT_MISMATCH",
                message="A source identity was redelivered with different content.",
            )

        await self._session.execute(
            pg_insert(RawEventProcessing)
            .values(
                raw_event_id=selected_id,
                user_id=user_id,
                state=RawEventState.RECEIVED,
                attempt_count=0,
            )
            .on_conflict_do_nothing(
                index_elements=[RawEventProcessing.raw_event_id],
            )
        )
        return StoredRawEvent(
            id=selected_id,
            created=inserted_id is not None,
            content_sha256=content_hash,
        )

    async def get_processing(
        self,
        user_id: UUID,
        raw_event_id: UUID,
        *,
        for_update: bool = False,
    ) -> RawEventProcessing:
        statement = select(RawEventProcessing).where(
            RawEventProcessing.raw_event_id == raw_event_id,
            RawEventProcessing.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        processing = await self._session.scalar(statement)
        if processing is None:
            msg = "Raw event is missing its processing state"
            raise RuntimeError(msg)
        return processing

    async def store_normalized_event(
        self,
        user_id: UUID,
        raw_event_id: UUID,
        event: NormalizedFinancialEventV1,
        *,
        normalizer_key: str,
        normalizer_version: str,
    ) -> NormalizedFinancialEvent:
        normalized_event_id = uuid4()
        statement = (
            pg_insert(NormalizedFinancialEvent)
            .values(
                id=normalized_event_id,
                user_id=user_id,
                raw_event_id=raw_event_id,
                schema_version=event.schema_version,
                normalizer_key=normalizer_key,
                normalizer_version=normalizer_version,
                event_kind=event.event_kind,
                amount=event.amount,
                currency=event.currency,
                description=event.description,
                occurred_at=event.occurred_at,
                merchant_name=event.merchant_name,
                counterparty=event.counterparty,
                category_hint=event.category_hint,
                tags=list(event.tags),
                confidence=event.confidence,
            )
            .on_conflict_do_nothing(
                constraint="uq_normalized_events_raw_contract",
            )
            .returning(NormalizedFinancialEvent.id)
        )
        inserted_id = (await self._session.execute(statement)).scalar_one_or_none()
        selected_id = inserted_id or await self._session.scalar(
            select(NormalizedFinancialEvent.id).where(
                NormalizedFinancialEvent.user_id == user_id,
                NormalizedFinancialEvent.raw_event_id == raw_event_id,
                NormalizedFinancialEvent.schema_version == event.schema_version,
                NormalizedFinancialEvent.normalizer_key == normalizer_key,
                NormalizedFinancialEvent.normalizer_version == normalizer_version,
            )
        )
        if selected_id is None:
            msg = "Normalized-event upsert did not return an owner-visible row"
            raise RuntimeError(msg)
        normalized = await self._session.scalar(
            select(NormalizedFinancialEvent).where(
                NormalizedFinancialEvent.id == selected_id,
                NormalizedFinancialEvent.user_id == user_id,
            )
        )
        if normalized is None:
            msg = "Normalized event disappeared after insertion"
            raise RuntimeError(msg)
        return normalized

    async def evidence_for_raw_event(
        self,
        user_id: UUID,
        raw_event_id: UUID,
    ) -> Evidence | None:
        return cast(
            Evidence | None,
            await self._session.scalar(
                select(Evidence).where(
                    Evidence.user_id == user_id,
                    Evidence.raw_event_id == raw_event_id,
                )
            ),
        )

    async def normalized_for_raw_event(
        self,
        user_id: UUID,
        raw_event_id: UUID,
    ) -> NormalizedFinancialEvent | None:
        return cast(
            NormalizedFinancialEvent | None,
            await self._session.scalar(
                select(NormalizedFinancialEvent)
                .where(
                    NormalizedFinancialEvent.user_id == user_id,
                    NormalizedFinancialEvent.raw_event_id == raw_event_id,
                )
                .order_by(NormalizedFinancialEvent.created_at.desc())
                .limit(1)
            ),
        )

    async def add_evidence(
        self,
        user_id: UUID,
        raw_event_id: UUID,
        normalized_event_id: UUID,
        transaction_id: UUID,
        *,
        locator: dict[str, Any],
        excerpt: str | None,
    ) -> Evidence:
        evidence = Evidence(
            user_id=user_id,
            raw_event_id=raw_event_id,
            normalized_event_id=normalized_event_id,
            transaction_id=transaction_id,
            evidence_kind=EvidenceKind.SOURCE_EVENT,
            locator=locator,
            excerpt=excerpt,
        )
        self._session.add(evidence)
        await self._session.flush()
        return evidence

    async def update_connection_cursor(
        self,
        user_id: UUID,
        connection_id: UUID,
        cursor: dict[str, Any],
        *,
        synced_at: datetime,
    ) -> None:
        connection = await self._session.scalar(
            select(SourceConnection)
            .where(
                SourceConnection.id == connection_id,
                SourceConnection.user_id == user_id,
            )
            .with_for_update()
        )
        if connection is None:
            raise IngestionConflictError(
                code="SOURCE_CONNECTION_NOT_FOUND",
                message="The source connection was not found.",
            )
        connection.cursor = cursor
        connection.last_synced_at = synced_at
        connection.last_error_code = None


def normalized_model_confidence(event: NormalizedFinancialEvent) -> Decimal | None:
    """Keep SQLAlchemy's decimal value explicit at the service boundary."""
    return Decimal(event.confidence) if event.confidence is not None else None
