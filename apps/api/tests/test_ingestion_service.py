"""PostgreSQL integration tests for replay-safe source-to-ledger ingestion."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.connectors.contracts import ConnectorEnvelope
from app.connectors.mock_receipt import MockReceiptConnector
from app.db.session import Database
from app.domain.enums import RawEventState, TransactionSource
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.errors import ConnectorContentError
from app.ingestion.service import IngestionService
from app.models import (
    Category,
    Evidence,
    LedgerTransaction,
    NormalizedFinancialEvent,
    RawEvent,
    RawEventProcessing,
    SourceConnection,
    User,
)

OWNER_ID = UUID("91000000-0000-4000-8000-000000000001")
WORK_CATEGORY_ID = UUID("92000000-0000-4000-8000-000000000001")
OCCURRED_AT = datetime(2026, 7, 24, 8, 30, tzinfo=UTC)


async def _seed_owner(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=OWNER_ID,
                email="pipeline-owner@example.test",
                name="Pipeline Owner",
                default_currency="INR",
                timezone="Asia/Kolkata",
            )
        )
        await session.flush()
        session.add(
            Category(
                id=WORK_CATEGORY_ID,
                name="Work Expense",
                normalized_name="work expense",
            )
        )


def _receipt(
    external_event_id: str | None = "receipt-001",
) -> ConnectorEnvelope:
    return ConnectorEnvelope(
        external_event_id=external_event_id,
        event_type="receipt",
        occurred_at=OCCURRED_AT,
        payload={
            "event_kind": "expense",
            "amount": "499.0000",
            "currency": "INR",
            "description": "Example Cloud monthly renewal",
            "merchant_name": "Example Cloud",
            "category_hint": "Work Expense",
            "tags": ["receipt", "subscription"],
            "confidence": "1.0000",
        },
        locator={"messageId": external_event_id or "content-only"},
        evidence_excerpt="Example Cloud receipt for INR 499",
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_mock_receipt_replay_creates_one_transaction_with_evidence(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    connector = MockReceiptConnector([_receipt()])
    service = IngestionService(isolated_database)

    first = await service.ingest_envelope(OWNER_ID, connector, _receipt())
    replay = await service.ingest_envelope(OWNER_ID, connector, _receipt())

    assert first.state is RawEventState.PROCESSED
    assert first.replayed is False
    assert first.transaction_id is not None
    assert replay.state is RawEventState.PROCESSED
    assert replay.replayed is True
    assert replay.raw_event_id == first.raw_event_id
    assert replay.normalized_event_id == first.normalized_event_id
    assert replay.transaction_id == first.transaction_id

    async with isolated_database.session_factory()() as session:
        counts = {
            "connections": await session.scalar(select(func.count(SourceConnection.id))),
            "raw": await session.scalar(select(func.count(RawEvent.id))),
            "normalized": await session.scalar(select(func.count(NormalizedFinancialEvent.id))),
            "transactions": await session.scalar(select(func.count(LedgerTransaction.id))),
            "evidence": await session.scalar(select(func.count(Evidence.id))),
        }
        transaction = await session.get(LedgerTransaction, first.transaction_id)
        processing = await session.get(RawEventProcessing, first.raw_event_id)
        evidence = await session.scalar(
            select(Evidence).where(Evidence.raw_event_id == first.raw_event_id)
        )

    assert counts == {
        "connections": 1,
        "raw": 1,
        "normalized": 1,
        "transactions": 1,
        "evidence": 1,
    }
    assert transaction is not None
    assert transaction.source is TransactionSource.INGESTION
    assert transaction.category_id == WORK_CATEGORY_ID
    assert processing is not None
    assert processing.attempt_count == 1
    assert evidence is not None
    assert evidence.excerpt == "Example Cloud receipt for INR 499"


@pytest.mark.database
@pytest.mark.asyncio
async def test_content_hash_fallback_is_replay_safe_without_external_id(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    connector = MockReceiptConnector(())
    service = IngestionService(isolated_database)
    envelope = _receipt(external_event_id=None)

    first = await service.ingest_envelope(OWNER_ID, connector, envelope)
    replay = await service.ingest_envelope(OWNER_ID, connector, envelope)

    assert first.raw_event_id == replay.raw_event_id
    assert first.transaction_id == replay.transaction_id
    assert replay.replayed is True


@pytest.mark.database
@pytest.mark.asyncio
async def test_concurrent_duplicate_delivery_serializes_canonical_handoff(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    connector = MockReceiptConnector(())
    service = IngestionService(isolated_database)
    envelope = _receipt()

    results = await asyncio.gather(
        service.ingest_envelope(OWNER_ID, connector, envelope),
        service.ingest_envelope(OWNER_ID, connector, envelope),
    )

    assert {result.raw_event_id for result in results} == {results[0].raw_event_id}
    assert {result.transaction_id for result in results} == {results[0].transaction_id}
    assert [result.replayed for result in results].count(True) == 1
    async with isolated_database.session_factory()() as session:
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 1
        assert await session.scalar(select(func.count(Evidence.id))) == 1


@pytest.mark.database
@pytest.mark.asyncio
async def test_failed_normalization_retains_raw_event_and_can_resume(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    connector = _FailOnceReceiptConnector()
    service = IngestionService(isolated_database)
    envelope = _receipt()

    failed = await service.ingest_envelope(OWNER_ID, connector, envelope)
    resumed = await service.ingest_envelope(OWNER_ID, connector, envelope)

    assert failed.state is RawEventState.FAILED
    assert failed.error_code == "SYNTHETIC_NORMALIZER_FAILURE"
    assert failed.transaction_id is None
    assert resumed.state is RawEventState.PROCESSED
    assert resumed.replayed is True
    assert resumed.transaction_id is not None
    async with isolated_database.session_factory()() as session:
        processing = await session.get(RawEventProcessing, failed.raw_event_id)
        assert await session.scalar(select(func.count(RawEvent.id))) == 1
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 1
    assert processing is not None
    assert processing.attempt_count == 2
    assert processing.last_error_code is None


@pytest.mark.database
@pytest.mark.asyncio
async def test_connector_sync_advances_cursor_after_durable_receipt(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    connector = MockReceiptConnector(
        [
            _receipt("receipt-001"),
            _receipt("receipt-002").model_copy(
                update={
                    "payload": {
                        **_receipt("receipt-002").payload,
                        "description": "Second cloud receipt",
                    }
                }
            ),
        ]
    )
    service = IngestionService(isolated_database)

    first = await service.sync_connector(OWNER_ID, connector)
    second = await service.sync_connector(OWNER_ID, connector)

    assert len(first.events) == 2
    assert all(item.state is RawEventState.PROCESSED for item in first.events)
    assert second.events == ()
    assert second.connection_id == first.connection_id
    async with isolated_database.session_factory()() as session:
        connection = await session.get(SourceConnection, first.connection_id)
    assert connection is not None
    assert connection.cursor == {"offset": 2}


class _FailOnceReceiptConnector(MockReceiptConnector):
    def __init__(self) -> None:
        super().__init__(())
        self._failed = False

    def normalize(self, envelope: ConnectorEnvelope) -> NormalizedFinancialEventV1:
        if not self._failed:
            self._failed = True
            raise ConnectorContentError(
                code="SYNTHETIC_NORMALIZER_FAILURE",
                message="Synthetic safe failure.",
            )
        return super().normalize(envelope)
