"""PostgreSQL integration coverage for reconciliation lifecycle guarantees."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.ai.extraction import FinancialNoteExtractor
from app.ai.mock import MockStructuredProvider
from app.ai.proposal_service import FinancialProposalService
from app.connectors.contracts import ConnectorEnvelope
from app.connectors.mock_receipt import MockReceiptConnector
from app.db.session import Database
from app.domain.enums import (
    ProposalStatus,
    RawEventState,
    ReconciliationActionType,
    ReconciliationStatus,
)
from app.ingestion.service import IngestionService
from app.models import (
    Evidence,
    FinancialEventProposal,
    LedgerTransaction,
    RawEventProcessing,
    ReconciliationAction,
    ReconciliationCase,
    User,
)
from app.reconciliation.errors import ReconciliationNotFoundError
from app.reconciliation.policy import ReconciliationPolicy
from app.reconciliation.service import ReconciliationService

OWNER_ID = UUID("e1000000-0000-4000-8000-000000000001")
OTHER_OWNER_ID = UUID("e1000000-0000-4000-8000-000000000002")
SOURCE_TIME = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)


async def _seed_owners(database: Database, *, include_other: bool = False) -> None:
    users = [
        User(
            id=OWNER_ID,
            email="reconciliation-owner@example.test",
            name="Reconciliation Owner",
            default_currency="INR",
            timezone="Asia/Kolkata",
        )
    ]
    if include_other:
        users.append(
            User(
                id=OTHER_OWNER_ID,
                email="reconciliation-other@example.test",
                name="Other Owner",
                default_currency="INR",
                timezone="Asia/Kolkata",
            )
        )
    async with database.session_factory()() as session, session.begin():
        session.add_all(users)


def _receipt(
    external_event_id: str,
    *,
    description: str = "Swiggy dinner order",
    merchant_name: str = "Swiggy",
    occurred_at: datetime = SOURCE_TIME,
    payment_identifiers: tuple[str, ...] = (),
) -> ConnectorEnvelope:
    return ConnectorEnvelope(
        external_event_id=external_event_id,
        event_type="receipt",
        occurred_at=occurred_at,
        payload={
            "event_kind": "expense",
            "amount": "480.0000",
            "currency": "INR",
            "description": description,
            "merchant_name": merchant_name,
            "tags": ["food"],
            "payment_identifiers": list(payment_identifiers),
            "confidence": "1.0000",
        },
        locator={"messageId": external_event_id},
        evidence_excerpt=f"{merchant_name} receipt for INR 480",
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_auto_merge_preserves_two_evidence_records_and_can_unmerge(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    connector = MockReceiptConnector(())
    ingestion = IngestionService(isolated_database)
    reconciliation = ReconciliationService(isolated_database, ReconciliationPolicy())

    first = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt("receipt-auto-1"),
    )
    merged = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt("receipt-auto-2", occurred_at=SOURCE_TIME + timedelta(minutes=1)),
    )

    assert first.state is RawEventState.PROCESSED
    assert merged.state is RawEventState.PROCESSED
    assert merged.transaction_id == first.transaction_id
    cases = await reconciliation.list(OWNER_ID, status=None)
    merged_case = next(case for case in cases if case.status is ReconciliationStatus.MERGED)
    assert merged_case.candidate_transaction_id == first.transaction_id
    assert merged_case.actions[0].action_type is ReconciliationActionType.AUTO_MERGED

    async with isolated_database.session_factory()() as session:
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 1
        assert await session.scalar(select(func.count(Evidence.id))) == 2

    unmerged = await reconciliation.unmerge(OWNER_ID, merged_case.id)

    assert unmerged.status is ReconciliationStatus.UNMERGED
    assert unmerged.resulting_transaction_id != first.transaction_id
    assert unmerged.actions[-1].action_type is ReconciliationActionType.USER_UNMERGED
    async with isolated_database.session_factory()() as session:
        evidence = await session.scalar(
            select(Evidence).where(
                Evidence.normalized_event_id == merged_case.normalized_event_id,
            )
        )
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 2
        assert await session.scalar(select(func.count(Evidence.id))) == 2
    assert evidence is not None
    assert evidence.transaction_id == unmerged.resulting_transaction_id


@pytest.mark.database
@pytest.mark.asyncio
async def test_ambiguous_candidate_waits_for_owner_merge_and_is_owner_scoped(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database, include_other=True)
    connector = MockReceiptConnector(())
    ingestion = IngestionService(isolated_database)
    reconciliation = ReconciliationService(isolated_database, ReconciliationPolicy())

    first = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt("receipt-review-1"),
    )
    pending_result = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt(
            "receipt-review-2",
            description="Card purchase",
            occurred_at=SOURCE_TIME + timedelta(minutes=1),
        ),
    )

    assert pending_result.state is RawEventState.NEEDS_REVIEW
    assert pending_result.transaction_id is None
    pending = await reconciliation.list(OWNER_ID)
    assert len(pending) == 1
    assert pending[0].candidate_transaction_id == first.transaction_id
    assert pending[0].actions[0].action_type is ReconciliationActionType.CANDIDATE_FLAGGED
    assert await reconciliation.list(OTHER_OWNER_ID) == ()
    with pytest.raises(ReconciliationNotFoundError):
        await reconciliation.merge(OTHER_OWNER_ID, pending[0].id)

    resolved = await reconciliation.merge(OWNER_ID, pending[0].id)

    assert resolved.status is ReconciliationStatus.MERGED
    assert resolved.resulting_transaction_id == first.transaction_id
    assert resolved.actions[-1].action_type is ReconciliationActionType.USER_MERGED
    async with isolated_database.session_factory()() as session:
        processing = await session.get(RawEventProcessing, pending_result.raw_event_id)
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 1
        assert await session.scalar(select(func.count(Evidence.id))) == 2
    assert processing is not None
    assert processing.state is RawEventState.PROCESSED


@pytest.mark.database
@pytest.mark.asyncio
async def test_owner_can_keep_ambiguous_event_as_a_separate_transaction(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    connector = MockReceiptConnector(())
    ingestion = IngestionService(isolated_database)
    reconciliation = ReconciliationService(isolated_database, ReconciliationPolicy())
    await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt("receipt-separate-1"),
    )
    pending_result = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt(
            "receipt-separate-2",
            description="Card purchase",
            occurred_at=SOURCE_TIME + timedelta(minutes=1),
        ),
    )
    pending = (await reconciliation.list(OWNER_ID))[0]

    resolved = await reconciliation.keep_separate(OWNER_ID, pending.id)

    assert resolved.status is ReconciliationStatus.KEPT_SEPARATE
    assert resolved.resulting_transaction_id != resolved.candidate_transaction_id
    assert resolved.actions[-1].action_type is ReconciliationActionType.USER_KEPT_SEPARATE
    async with isolated_database.session_factory()() as session:
        processing = await session.get(RawEventProcessing, pending_result.raw_event_id)
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 2
        assert await session.scalar(select(func.count(Evidence.id))) == 2
    assert processing is not None
    assert processing.state is RawEventState.PROCESSED


@pytest.mark.database
@pytest.mark.asyncio
async def test_exact_typed_identifier_matches_outside_candidate_time_window(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    connector = MockReceiptConnector(())
    ingestion = IngestionService(isolated_database)
    payment_id = ("upi:123456789012",)

    first = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt("receipt-id-1", payment_identifiers=payment_id),
    )
    duplicate = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt(
            "receipt-id-2",
            description="Different wording",
            merchant_name="Different merchant",
            occurred_at=SOURCE_TIME + timedelta(days=5),
            payment_identifiers=payment_id,
        ),
    )

    assert duplicate.state is RawEventState.PROCESSED
    assert duplicate.transaction_id == first.transaction_id
    async with isolated_database.session_factory()() as session:
        exact_case = await session.scalar(
            select(ReconciliationCase).where(
                ReconciliationCase.normalized_event_id == duplicate.normalized_event_id,
            )
        )
    assert exact_case is not None
    assert exact_case.score == Decimal("1.0000")
    assert exact_case.reasons[0] == "PAYMENT_IDENTIFIER_EXACT"


@pytest.mark.database
@pytest.mark.asyncio
async def test_concurrent_distinct_deliveries_share_one_canonical_transaction(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    connector = MockReceiptConnector(())
    ingestion = IngestionService(isolated_database)

    results = await asyncio.gather(
        ingestion.ingest_envelope(
            OWNER_ID,
            connector,
            _receipt("receipt-concurrent-1"),
        ),
        ingestion.ingest_envelope(
            OWNER_ID,
            connector,
            _receipt("receipt-concurrent-2"),
        ),
    )

    assert results[0].transaction_id == results[1].transaction_id
    async with isolated_database.session_factory()() as session:
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 1
        assert await session.scalar(select(func.count(Evidence.id))) == 2
        assert await session.scalar(select(func.count(ReconciliationCase.id))) == 2
        assert await session.scalar(select(func.count(ReconciliationAction.id))) == 2


@pytest.mark.database
@pytest.mark.asyncio
async def test_proposal_approval_pauses_for_reconciliation_then_completes(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    connector = MockReceiptConnector(())
    ingestion = IngestionService(isolated_database)
    existing = await ingestion.ingest_envelope(
        OWNER_ID,
        connector,
        _receipt("receipt-proposal-existing"),
    )
    provider = MockStructuredProvider(
        [
            {
                "event_kind": "expense",
                "amount": "480.0000",
                "currency": "INR",
                "description": "Card purchase",
                "occurred_at": SOURCE_TIME.isoformat(),
                "merchant_name": "Swiggy",
                "tags": ["food"],
                "confidence": "0.9500",
            }
        ]
    )
    proposals = FinancialProposalService(
        isolated_database,
        FinancialNoteExtractor(
            provider,
            max_input_chars=8_000,
            review_confidence_threshold=Decimal("0.8500"),
        ),
    )
    reconciliation = ReconciliationService(isolated_database, ReconciliationPolicy())
    proposal = await proposals.submit_manual_note(
        OWNER_ID,
        note="Paid INR 480 by card",
        source_timestamp=SOURCE_TIME,
        client_request_id=UUID("e2000000-0000-4000-8000-000000000001"),
    )

    reviewed = await proposals.approve(OWNER_ID, proposal.id)

    assert reviewed.status is ProposalStatus.RECONCILIATION_REVIEW
    assert reviewed.canonical_target_id is None
    case = (await reconciliation.list(OWNER_ID))[0]
    resolved = await reconciliation.merge(OWNER_ID, case.id)
    assert resolved.resulting_transaction_id == existing.transaction_id
    approved = (await proposals.list(OWNER_ID, status=ProposalStatus.APPROVED))[0]
    assert approved.id == proposal.id
    assert approved.canonical_target_id == existing.transaction_id
    async with isolated_database.session_factory()() as session:
        stored = await session.get(FinancialEventProposal, proposal.id)
    assert stored is not None
    assert stored.status is ProposalStatus.APPROVED
