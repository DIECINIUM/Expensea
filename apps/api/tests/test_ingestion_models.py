"""Database invariants for replay-safe ingestion and provenance."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import Database
from app.domain.enums import (
    ConnectorType,
    EvidenceKind,
    NormalizedEventKind,
    RawEventState,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models import (
    Evidence,
    LedgerTransaction,
    NormalizedFinancialEvent,
    RawEvent,
    RawEventProcessing,
    SourceConnection,
    User,
)

OWNER_ID = UUID("81000000-0000-4000-8000-000000000001")
OTHER_USER_ID = UUID("82000000-0000-4000-8000-000000000001")
CONNECTION_ID = UUID("83000000-0000-4000-8000-000000000001")
RAW_EVENT_ID = UUID("84000000-0000-4000-8000-000000000001")
NORMALIZED_EVENT_ID = UUID("85000000-0000-4000-8000-000000000001")
TRANSACTION_ID = UUID("86000000-0000-4000-8000-000000000001")
OCCURRED_AT = datetime(2026, 7, 24, 8, 30, tzinfo=UTC)
CONTENT_HASH = "8e85be58c1c372ac29fe7bfa80d8ddcb4067b1ec789323a76e4c6f4d680e0c37"


async def _seed_owners(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add_all(
            [
                User(
                    id=OWNER_ID,
                    email="ingestion-owner@example.test",
                    name="Ingestion Owner",
                    default_currency="INR",
                    timezone="Asia/Kolkata",
                ),
                User(
                    id=OTHER_USER_ID,
                    email="ingestion-other@example.test",
                    name="Ingestion Other",
                    default_currency="INR",
                    timezone="UTC",
                ),
            ]
        )


@pytest.mark.database
@pytest.mark.asyncio
async def test_ingestion_provenance_round_trips_with_owner_aware_links(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    async with isolated_database.session_factory()() as session, session.begin():
        connection = SourceConnection(
            id=CONNECTION_ID,
            user_id=OWNER_ID,
            connector_type=ConnectorType.MOCK_RECEIPT,
            connection_key="default",
            display_name="Mock receipts",
        )
        session.add(connection)
        await session.flush()

        raw_event = RawEvent(
            id=RAW_EVENT_ID,
            user_id=OWNER_ID,
            source_connection_id=CONNECTION_ID,
            identity_key="external:receipt-001",
            external_event_id="receipt-001",
            content_sha256=CONTENT_HASH,
            source_event_type="receipt",
            occurred_at=OCCURRED_AT,
            payload={"amount": "499.00", "currency": "INR"},
        )
        session.add(raw_event)
        await session.flush()

        processing = RawEventProcessing(
            raw_event_id=RAW_EVENT_ID,
            user_id=OWNER_ID,
            state=RawEventState.PROCESSED,
            attempt_count=1,
        )
        normalized = NormalizedFinancialEvent(
            id=NORMALIZED_EVENT_ID,
            user_id=OWNER_ID,
            raw_event_id=RAW_EVENT_ID,
            schema_version="financial-event/v1",
            normalizer_key="mock_receipt",
            normalizer_version="1",
            event_kind=NormalizedEventKind.EXPENSE,
            amount=Decimal("499.0000"),
            currency="INR",
            description="Mock cloud receipt",
            occurred_at=OCCURRED_AT,
            merchant_name="Example Cloud",
            category_hint="Work Expense",
            tags=["receipt", "subscription"],
            confidence=Decimal("1.0000"),
        )
        transaction = LedgerTransaction(
            id=TRANSACTION_ID,
            user_id=OWNER_ID,
            amount=Decimal("499.0000"),
            currency="INR",
            transaction_type=TransactionType.EXPENSE,
            description="Mock cloud receipt",
            transaction_date=OCCURRED_AT,
            source=TransactionSource.INGESTION,
            confidence=Decimal("1.0000"),
            status=TransactionStatus.POSTED,
        )
        evidence = Evidence(
            user_id=OWNER_ID,
            raw_event_id=RAW_EVENT_ID,
            normalized_event_id=NORMALIZED_EVENT_ID,
            transaction_id=TRANSACTION_ID,
            evidence_kind=EvidenceKind.SOURCE_EVENT,
            locator={"externalEventId": "receipt-001"},
            excerpt="Example Cloud receipt",
        )
        session.add_all([processing, normalized, transaction])
        await session.flush()
        session.add(evidence)

    async with isolated_database.session_factory()() as session:
        stored_evidence = await session.get(Evidence, evidence.id)
        stored_processing = await session.get(RawEventProcessing, RAW_EVENT_ID)
        stored_transaction = await session.get(LedgerTransaction, TRANSACTION_ID)

    assert stored_evidence is not None
    assert stored_evidence.transaction_id == TRANSACTION_ID
    assert stored_processing is not None
    assert stored_processing.state is RawEventState.PROCESSED
    assert stored_transaction is not None
    assert stored_transaction.source is TransactionSource.INGESTION


@pytest.mark.database
@pytest.mark.asyncio
async def test_raw_event_identity_is_unique_per_connection(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    async with isolated_database.session_factory()() as session, session.begin():
        session.add(
            SourceConnection(
                id=CONNECTION_ID,
                user_id=OWNER_ID,
                connector_type=ConnectorType.MOCK_RECEIPT,
                connection_key="default",
                display_name="Mock receipts",
            )
        )
        await session.flush()
        session.add(
            RawEvent(
                user_id=OWNER_ID,
                source_connection_id=CONNECTION_ID,
                identity_key=f"sha256:{CONTENT_HASH}",
                content_sha256=CONTENT_HASH,
                source_event_type="receipt",
                payload={"description": "first"},
            )
        )

    async with isolated_database.session_factory()() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    RawEvent(
                        user_id=OWNER_ID,
                        source_connection_id=CONNECTION_ID,
                        identity_key=f"sha256:{CONTENT_HASH}",
                        content_sha256=CONTENT_HASH,
                        source_event_type="receipt",
                        payload={"description": "duplicate delivery"},
                    )
                )


@pytest.mark.database
@pytest.mark.asyncio
async def test_raw_event_cannot_reference_another_users_connection(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    async with isolated_database.session_factory()() as session, session.begin():
        session.add(
            SourceConnection(
                id=CONNECTION_ID,
                user_id=OWNER_ID,
                connector_type=ConnectorType.MOCK_RECEIPT,
                connection_key="default",
                display_name="Mock receipts",
            )
        )

    async with isolated_database.session_factory()() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    RawEvent(
                        user_id=OTHER_USER_ID,
                        source_connection_id=CONNECTION_ID,
                        identity_key="external:cross-owner",
                        external_event_id="cross-owner",
                        content_sha256=CONTENT_HASH,
                        source_event_type="receipt",
                        payload={"description": "must not persist"},
                    )
                )
