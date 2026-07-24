"""Manual/source note extraction, review queue, and deterministic approval."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIError, AIOutputError, ProposalReviewError
from app.ai.extraction import (
    FinancialNoteExtractor,
    NoteExtractionContext,
)
from app.ai.prompts.financial_note_v1 import (
    PROMPT_NAME,
    PROMPT_VERSION,
    SCHEMA_VERSION,
)
from app.ai.proposal_dto import FinancialEventProposalView
from app.ai.proposal_repository import (
    ProposalRepository,
    proposal_view_from_model,
)
from app.connectors.manual_note import (
    ManualNoteConnector,
    create_manual_note_envelope,
)
from app.db.session import Database
from app.domain.enums import (
    NormalizedEventKind,
    ProposalStatus,
    RawEventState,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.domain.normalization import normalize_lookup_text
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.repository import IngestionRepository
from app.ingestion.service import IngestionService
from app.ingestion.state import require_state_transition
from app.ledger.commands import parse_create_transaction
from app.ledger.obligation_commands import (
    parse_create_obligation,
    parse_create_person,
)
from app.ledger.obligation_repository import ObligationRepository
from app.ledger.periods import parse_timezone
from app.ledger.recurring_commands import parse_create_recurring_payment
from app.ledger.recurring_repository import RecurringPaymentRepository
from app.ledger.repository import LedgerRepository
from app.models import FinancialEventProposal, RawEventProcessing

Clock = Callable[[], datetime]

_TRANSACTION_TYPES: dict[NormalizedEventKind, TransactionType] = {
    NormalizedEventKind.EXPENSE: TransactionType.EXPENSE,
    NormalizedEventKind.INCOME: TransactionType.INCOME,
    NormalizedEventKind.TRANSFER: TransactionType.TRANSFER,
    NormalizedEventKind.REFUND: TransactionType.REFUND,
    NormalizedEventKind.SHARED_EXPENSE: TransactionType.SHARED_EXPENSE,
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FinancialProposalService:
    """Persist traceable model proposals and require explicit review before writes."""

    def __init__(
        self,
        database: Database,
        extractor: FinancialNoteExtractor,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._database = database
        self._extractor = extractor
        self._clock = clock
        self._ingestion = IngestionService(database)

    async def submit_manual_note(
        self,
        user_id: UUID,
        *,
        note: str,
        source_timestamp: datetime,
        client_request_id: UUID,
        labels: Iterable[str] = (),
    ) -> FinancialEventProposalView:
        """Create/replay a raw note, extract it once, and queue it for review."""
        envelope = create_manual_note_envelope(
            note,
            source_timestamp=source_timestamp,
            note_id=client_request_id,
            labels=labels,
        )
        connector = ManualNoteConnector()
        ingested = await self._ingestion.ingest_envelope(
            user_id,
            connector,
            envelope,
        )
        return await self.extract_raw_event(user_id, ingested.raw_event_id)

    async def extract_raw_event(
        self,
        user_id: UUID,
        raw_event_id: UUID,
    ) -> FinancialEventProposalView:
        """Interpret one owner-visible raw event and persist safe model metadata."""
        async with self._database.session_factory()() as session:
            repository = ProposalRepository(session)
            existing = await repository.existing_for_prompt(
                user_id,
                raw_event_id,
                prompt_name=PROMPT_NAME,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
            )
            if existing is not None:
                return existing
            raw_context = await repository.raw_extraction_context(user_id, raw_event_id)
        if raw_context is None:
            raise ProposalReviewError(
                code="RAW_EVENT_NOT_FOUND",
                message="The source event was not found.",
            )

        extraction_text = raw_context.payload.get("extraction_text")
        if not isinstance(extraction_text, str) or not extraction_text.strip():
            raise ProposalReviewError(
                code="SOURCE_TEXT_NOT_AVAILABLE",
                message="The source event has no supported text to extract.",
            )
        source_timestamp = raw_context.occurred_at or self._now()
        try:
            extraction = await self._extractor.extract(
                extraction_text,
                NoteExtractionContext(
                    source_timestamp=source_timestamp,
                    timezone=raw_context.timezone,
                    default_currency=raw_context.default_currency,
                ),
            )
        except AIError as exc:
            await self._record_extraction_failure(user_id, raw_event_id, exc.code)
            raise

        async with self._database.session_factory()() as session, session.begin():
            repository = ProposalRepository(session)
            proposal = await repository.create_or_get(
                user_id,
                raw_context,
                extraction,
            )
            processing = await IngestionRepository(session).get_processing(
                user_id,
                raw_event_id,
                for_update=True,
            )
            processing.last_error_code = None
            return proposal

    async def list(
        self,
        user_id: UUID,
        *,
        status: ProposalStatus | None = ProposalStatus.NEEDS_REVIEW,
    ) -> tuple[FinancialEventProposalView, ...]:
        """Return the owner review queue without exposing raw source text."""
        async with self._database.session_factory()() as session:
            return await ProposalRepository(session).list(user_id, status=status)

    async def reject(
        self,
        user_id: UUID,
        proposal_id: UUID,
    ) -> FinancialEventProposalView:
        """Reject one locked pending proposal without creating canonical data."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ProposalRepository(session)
            proposal = self._require_pending(await repository.lock(user_id, proposal_id))
            source = await repository.source_for_proposal(user_id, proposal)
            proposal.status = ProposalStatus.REJECTED
            processing = await IngestionRepository(session).get_processing(
                user_id,
                proposal.raw_event_id,
                for_update=True,
            )
            processing.last_error_code = "USER_REJECTED"
            await repository.flush()
            return proposal_view_from_model(proposal, source)

    async def approve(
        self,
        user_id: UUID,
        proposal_id: UUID,
    ) -> FinancialEventProposalView:
        """Convert one locked proposal through existing deterministic repositories."""
        async with self._database.session_factory()() as session, session.begin():
            proposals = ProposalRepository(session)
            proposal = self._require_pending(await proposals.lock(user_id, proposal_id))
            source = await proposals.source_for_proposal(user_id, proposal)
            processing = await IngestionRepository(session).get_processing(
                user_id,
                proposal.raw_event_id,
                for_update=True,
            )
            normalized = self._normalized_contract(proposal)
            normalized_model = await IngestionRepository(session).store_normalized_event(
                user_id,
                proposal.raw_event_id,
                normalized,
                normalizer_key=PROMPT_NAME,
                normalizer_version=proposal.prompt_version,
            )

            transaction_type = _TRANSACTION_TYPES.get(proposal.event_kind)
            if transaction_type is not None:
                proposal.transaction_id = await self._approve_transaction(
                    user_id,
                    proposal,
                    transaction_type,
                    normalized_model.id,
                    processing,
                    session,
                )
            elif proposal.event_kind is NormalizedEventKind.RECEIVABLE:
                proposal.receivable_id = await self._approve_obligation(
                    user_id,
                    proposal,
                    receivable=True,
                    session=session,
                )
            elif proposal.event_kind is NormalizedEventKind.PAYABLE:
                proposal.payable_id = await self._approve_obligation(
                    user_id,
                    proposal,
                    receivable=False,
                    session=session,
                )
            elif proposal.event_kind is NormalizedEventKind.RECURRING:
                proposal.recurring_payment_id = await self._approve_recurring(
                    user_id,
                    proposal,
                    session=session,
                )
            else:
                raise ProposalReviewError(
                    code="PROPOSAL_KIND_NOT_APPROVABLE",
                    message="This extracted event kind cannot be approved.",
                )

            require_state_transition(processing.state, RawEventState.PROCESSED)
            processing.state = RawEventState.PROCESSED
            processing.last_error_code = None
            proposal.status = ProposalStatus.APPROVED
            await proposals.flush()
            return proposal_view_from_model(proposal, source)

    async def _approve_transaction(
        self,
        user_id: UUID,
        proposal: FinancialEventProposal,
        transaction_type: TransactionType,
        normalized_event_id: UUID,
        processing: RawEventProcessing,
        session: AsyncSession,
    ) -> UUID:
        amount, currency, occurred_at = self._require_money_and_occurred(proposal)
        ledger = LedgerRepository(session)
        category_id = None
        if proposal.category_hint is not None:
            category_id = await ledger.find_visible_category_id(
                user_id,
                normalize_lookup_text(proposal.category_hint),
            )
        command = parse_create_transaction(
            amount=format(amount, "f"),
            currency=currency,
            transaction_type=transaction_type,
            description=proposal.description,
            transaction_date=occurred_at,
            status=TransactionStatus.POSTED,
            category_id=category_id,
            merchant_name=proposal.merchant_name,
            source=TransactionSource.INGESTION,
            confidence=proposal.confidence,
        )
        transaction = await ledger.create_transaction(user_id, command)
        await IngestionRepository(session).add_evidence(
            user_id,
            processing.raw_event_id,
            normalized_event_id,
            transaction.id,
            locator={"proposalId": str(proposal.id)},
            excerpt=None,
        )
        return transaction.id

    async def _approve_obligation(
        self,
        user_id: UUID,
        proposal: FinancialEventProposal,
        *,
        receivable: bool,
        session: AsyncSession,
    ) -> UUID:
        amount, currency, occurred_at = self._require_money_and_occurred(proposal)
        if proposal.counterparty is None:
            raise ProposalReviewError(
                code="PROPOSAL_COUNTERPARTY_REQUIRED",
                message="A receivable or payable needs a counterparty before approval.",
            )
        repository = ObligationRepository(session)
        timezone_name = await repository.owner_timezone(user_id)
        if timezone_name is None:
            raise ProposalReviewError(
                code="PROFILE_NOT_FOUND",
                message="The ledger profile was not found.",
            )
        person_command = parse_create_person(name=proposal.counterparty)
        person = await repository.create_person(user_id, person_command)
        if person is None:
            person = await repository.find_person_by_normalized_name(
                user_id,
                person_command.normalized_name,
            )
        if person is None:
            msg = "Person upsert completed without an owner-visible row"
            raise RuntimeError(msg)
        timezone = parse_timezone(timezone_name)
        issued_date = occurred_at.astimezone(timezone).date()
        command = parse_create_obligation(
            person_id=person.id,
            amount=format(amount, "f"),
            currency=currency,
            description=proposal.description,
            issued_date=issued_date,
            due_date=proposal.due_date,
        )
        as_of = self._now().astimezone(timezone).date()
        if receivable:
            obligation = await repository.create_receivable(
                user_id,
                command,
                as_of=as_of,
            )
        else:
            obligation = await repository.create_payable(
                user_id,
                command,
                as_of=as_of,
            )
        return obligation.id

    async def _approve_recurring(
        self,
        user_id: UUID,
        proposal: FinancialEventProposal,
        *,
        session: AsyncSession,
    ) -> UUID:
        if (
            proposal.amount is None
            or proposal.currency is None
            or proposal.merchant_name is None
            or proposal.recurrence_rule is None
            or proposal.next_expected_date is None
        ):
            raise ProposalReviewError(
                code="PROPOSAL_RECURRING_FIELDS_REQUIRED",
                message="A recurring payment needs amount, merchant, rule, and next date.",
            )
        command = parse_create_recurring_payment(
            amount=format(proposal.amount, "f"),
            currency=proposal.currency,
            merchant_name=proposal.merchant_name,
            recurrence_rule=proposal.recurrence_rule,
            next_expected_date=proposal.next_expected_date,
        )
        repository = RecurringPaymentRepository(session)
        if not await repository.user_exists(user_id):
            raise ProposalReviewError(
                code="PROFILE_NOT_FOUND",
                message="The ledger profile was not found.",
            )
        merchant_id = await repository.get_or_create_merchant(command)
        payment = await repository.create(user_id, merchant_id, command)
        return payment.id

    async def _record_extraction_failure(
        self,
        user_id: UUID,
        raw_event_id: UUID,
        error_code: str,
    ) -> None:
        async with self._database.session_factory()() as session, session.begin():
            processing = await IngestionRepository(session).get_processing(
                user_id,
                raw_event_id,
                for_update=True,
            )
            processing.last_error_code = error_code

    @staticmethod
    def _require_pending(
        proposal: FinancialEventProposal | None,
    ) -> FinancialEventProposal:
        if proposal is None:
            raise ProposalReviewError(
                code="PROPOSAL_NOT_FOUND",
                message="The financial event proposal was not found.",
            )
        if proposal.status is not ProposalStatus.NEEDS_REVIEW:
            raise ProposalReviewError(
                code="PROPOSAL_ALREADY_REVIEWED",
                message="The financial event proposal has already been reviewed.",
            )
        return proposal

    @staticmethod
    def _normalized_contract(
        proposal: FinancialEventProposal,
    ) -> NormalizedFinancialEventV1:
        return NormalizedFinancialEventV1(
            event_kind=proposal.event_kind,
            amount=proposal.amount,
            currency=proposal.currency,
            description=proposal.description,
            occurred_at=proposal.occurred_at,
            merchant_name=proposal.merchant_name,
            counterparty=proposal.counterparty,
            category_hint=proposal.category_hint,
            tags=tuple(proposal.tags),
            confidence=proposal.confidence,
        )

    @staticmethod
    def _require_money_and_occurred(
        proposal: FinancialEventProposal,
    ) -> tuple[Decimal, str, datetime]:
        if proposal.amount is None or proposal.currency is None or proposal.occurred_at is None:
            raise ProposalReviewError(
                code="PROPOSAL_FINANCIAL_FIELDS_REQUIRED",
                message="Amount, currency, and occurrence time are required before approval.",
            )
        return proposal.amount, proposal.currency, proposal.occurred_at

    def _now(self) -> datetime:
        instant = self._clock()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise AIOutputError(
                code="INVALID_PROPOSAL_CLOCK",
                message="The proposal service clock must include a timezone offset.",
            )
        return instant.astimezone(UTC)
