"""PostgreSQL integration tests for extraction persistence and review actions."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.ai.errors import AIProviderError, ProposalReviewError
from app.ai.extraction import FinancialNoteExtractor
from app.ai.mock import MockStructuredProvider
from app.ai.proposal_service import FinancialProposalService
from app.db.session import Database
from app.domain.enums import ProposalStatus, RawEventState, TransactionSource
from app.models import (
    Evidence,
    FinancialEventProposal,
    LedgerTransaction,
    Person,
    RawEvent,
    RawEventProcessing,
    Receivable,
    User,
)

OWNER_ID = UUID("c1000000-0000-4000-8000-000000000001")
REQUEST_ID = UUID("c2000000-0000-4000-8000-000000000001")
SOURCE_TIMESTAMP = datetime(2026, 7, 24, 4, 30, tzinfo=UTC)
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


async def _seed_owner(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=OWNER_ID,
                email="proposal-owner@example.test",
                name="Proposal Owner",
                default_currency="INR",
                timezone="Asia/Kolkata",
            )
        )


def _service(
    database: Database,
    responses: list[dict[str, object]],
) -> tuple[FinancialProposalService, MockStructuredProvider]:
    provider = MockStructuredProvider(responses)
    extractor = FinancialNoteExtractor(
        provider,
        max_input_chars=8_000,
        review_confidence_threshold=Decimal("0.8500"),
    )
    return (
        FinancialProposalService(
            database,
            extractor,
            clock=lambda: NOW,
        ),
        provider,
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_manual_note_replay_persists_one_traceable_proposal(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    service, provider = _service(
        isolated_database,
        [
            {
                "event_kind": "expense",
                "amount": "249.0000",
                "currency": "INR",
                "description": "Music subscription",
                "occurred_at": "2026-07-24T10:00:00+05:30",
                "merchant_name": "Example Music",
                "category_hint": "Entertainment",
                "tags": ["subscription", "music"],
                "confidence": "0.9300",
            }
        ],
    )

    first = await service.submit_manual_note(
        OWNER_ID,
        note="Paid ₹249 for music subscription today",
        source_timestamp=SOURCE_TIMESTAMP,
        client_request_id=REQUEST_ID,
        labels=["Personal"],
    )
    replay = await service.submit_manual_note(
        OWNER_ID,
        note="Paid ₹249 for music subscription today",
        source_timestamp=SOURCE_TIMESTAMP,
        client_request_id=REQUEST_ID,
        labels=["Personal"],
    )
    queue = await service.list(OWNER_ID)

    assert first == replay
    assert first.status is ProposalStatus.NEEDS_REVIEW
    assert first.tags == ("subscription", "music")
    assert first.source.value == "manual_note"
    assert queue == (first,)
    assert len(provider.requests) == 1
    async with isolated_database.session_factory()() as session:
        assert await session.scalar(select(func.count(RawEvent.id))) == 1
        assert await session.scalar(select(func.count(FinancialEventProposal.id))) == 1
        processing = await session.get(RawEventProcessing, first.raw_event_id)
    assert processing is not None
    assert processing.state is RawEventState.NEEDS_REVIEW


@pytest.mark.database
@pytest.mark.asyncio
async def test_approving_expense_creates_one_transaction_and_evidence(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    service, _ = _service(
        isolated_database,
        [
            {
                "event_kind": "expense",
                "amount": "450.0000",
                "currency": "INR",
                "description": "Airport cab",
                "occurred_at": "2026-07-24T10:00:00+05:30",
                "merchant_name": "Example Cabs",
                "category_hint": "Travel",
                "tags": ["cab", "travel"],
                "confidence": "0.9100",
            }
        ],
    )
    proposal = await service.submit_manual_note(
        OWNER_ID,
        note="Paid ₹450 for airport cab",
        source_timestamp=SOURCE_TIMESTAMP,
        client_request_id=REQUEST_ID,
    )

    approved = await service.approve(OWNER_ID, proposal.id)

    assert approved.status is ProposalStatus.APPROVED
    assert approved.canonical_target_type == "transaction"
    assert approved.canonical_target_id is not None
    assert await service.list(OWNER_ID) == ()
    async with isolated_database.session_factory()() as session:
        transaction = await session.get(
            LedgerTransaction,
            approved.canonical_target_id,
        )
        processing = await session.get(RawEventProcessing, proposal.raw_event_id)
        evidence_count = await session.scalar(select(func.count(Evidence.id)))
    assert transaction is not None
    assert transaction.amount == Decimal("450.0000")
    assert transaction.source is TransactionSource.INGESTION
    assert processing is not None
    assert processing.state is RawEventState.PROCESSED
    assert evidence_count == 1

    with pytest.raises(ProposalReviewError) as stale:
        await service.approve(OWNER_ID, proposal.id)
    assert stale.value.code == "PROPOSAL_ALREADY_REVIEWED"


@pytest.mark.database
@pytest.mark.asyncio
async def test_receivable_approval_creates_person_and_obligation_with_provenance(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    service, _ = _service(
        isolated_database,
        [
            {
                "event_kind": "receivable",
                "amount": "800.0000",
                "currency": "INR",
                "description": "Cab fare lent to Priya",
                "occurred_at": "2026-07-24T10:00:00+05:30",
                "due_date": "2026-07-31",
                "counterparty": "Priya",
                "category_hint": "Travel",
                "tags": ["friend", "cab"],
                "confidence": "0.9400",
            }
        ],
    )
    proposal = await service.submit_manual_note(
        OWNER_ID,
        note="Lent Priya ₹800 for cab today; she will repay Friday",
        source_timestamp=SOURCE_TIMESTAMP,
        client_request_id=REQUEST_ID,
    )

    approved = await service.approve(OWNER_ID, proposal.id)

    assert approved.status is ProposalStatus.APPROVED
    assert approved.canonical_target_type == "receivable"
    assert approved.canonical_target_id is not None
    async with isolated_database.session_factory()() as session:
        receivable = await session.get(Receivable, approved.canonical_target_id)
        person = await session.scalar(
            select(Person).where(
                Person.user_id == OWNER_ID,
                Person.normalized_name == "priya",
            )
        )
        stored_proposal = await session.get(FinancialEventProposal, proposal.id)
    assert receivable is not None
    assert receivable.amount == Decimal("800.0000")
    assert receivable.due_date is not None
    assert person is not None
    assert stored_proposal is not None
    assert stored_proposal.raw_event_id == proposal.raw_event_id
    assert stored_proposal.receivable_id == receivable.id


@pytest.mark.database
@pytest.mark.asyncio
async def test_rejection_and_provider_failure_never_create_canonical_records(
    isolated_database: Database,
) -> None:
    await _seed_owner(isolated_database)
    service, _ = _service(
        isolated_database,
        [
            {
                "event_kind": "expense",
                "amount": "10.0000",
                "currency": "INR",
                "description": "Unwanted proposal",
                "occurred_at": "2026-07-24T10:00:00+05:30",
                "confidence": "0.5000",
            }
        ],
    )
    proposal = await service.submit_manual_note(
        OWNER_ID,
        note="Maybe spent ₹10",
        source_timestamp=SOURCE_TIMESTAMP,
        client_request_id=REQUEST_ID,
    )

    rejected = await service.reject(OWNER_ID, proposal.id)

    assert rejected.status is ProposalStatus.REJECTED
    assert rejected.canonical_target_id is None
    async with isolated_database.session_factory()() as session:
        assert await session.scalar(select(func.count(LedgerTransaction.id))) == 0
        assert await session.scalar(select(func.count(Evidence.id))) == 0

    failing_service, _ = _service(isolated_database, [])
    with pytest.raises(AIProviderError) as failed:
        await failing_service.submit_manual_note(
            OWNER_ID,
            note="Another note",
            source_timestamp=SOURCE_TIMESTAMP,
            client_request_id=UUID("c2000000-0000-4000-8000-000000000002"),
        )
    assert failed.value.code == "MOCK_PROVIDER_EXHAUSTED"
    async with isolated_database.session_factory()() as session:
        assert await session.scalar(select(func.count(FinancialEventProposal.id))) == 1
        processing = await session.scalar(
            select(RawEventProcessing).where(
                RawEventProcessing.last_error_code == "MOCK_PROVIDER_EXHAUSTED"
            )
        )
    assert processing is not None
