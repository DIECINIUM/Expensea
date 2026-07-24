"""Atomic reconciliation handoff, owner review, and safe unmerge."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.domain.enums import (
    NormalizedEventKind,
    ProposalStatus,
    RawEventState,
    ReconciliationActionType,
    ReconciliationDecision,
    ReconciliationStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.domain.normalization import normalize_lookup_text
from app.ingestion.repository import IngestionRepository, normalized_model_confidence
from app.ingestion.state import require_state_transition
from app.ledger.commands import CreateTransactionCommand, parse_create_transaction
from app.ledger.repository import LedgerRepository
from app.models import LedgerTransaction, NormalizedFinancialEvent, ReconciliationCase
from app.reconciliation.dto import (
    ReconciliationCaseView,
    ReconciliationProcessingOutcome,
)
from app.reconciliation.errors import (
    ReconciliationConflictError,
    ReconciliationNotFoundError,
)
from app.reconciliation.policy import ReconciliationPolicy
from app.reconciliation.repository import ReconciliationRepository
from app.reconciliation.scoring import SCORE_VERSION, reconcile_candidates

_TRANSACTION_TYPES: dict[NormalizedEventKind, TransactionType] = {
    NormalizedEventKind.EXPENSE: TransactionType.EXPENSE,
    NormalizedEventKind.INCOME: TransactionType.INCOME,
    NormalizedEventKind.TRANSFER: TransactionType.TRANSFER,
    NormalizedEventKind.REFUND: TransactionType.REFUND,
    NormalizedEventKind.SHARED_EXPENSE: TransactionType.SHARED_EXPENSE,
}


class ReconciliationCoordinator:
    """Session-scoped canonical handoff shared by ingestion and AI approval."""

    def __init__(self, policy: ReconciliationPolicy) -> None:
        self._policy = policy

    async def reconcile_transaction(
        self,
        user_id: UUID,
        event: NormalizedFinancialEvent,
        command: CreateTransactionCommand,
        *,
        evidence_locator: dict[str, Any],
        evidence_excerpt: str | None,
        session: AsyncSession,
    ) -> ReconciliationProcessingOutcome:
        """Choose merge/review/new and persist its evidence and audit atomically."""
        repository = ReconciliationRepository(session)
        ingestion = IngestionRepository(session)
        ledger = LedgerRepository(session)
        await repository.acquire_user_write_lock(user_id)
        candidates = await repository.find_candidates(
            user_id,
            event,
            command.transaction_type,
            self._policy,
        )
        result = reconcile_candidates(event, candidates, self._policy)

        if result.decision is ReconciliationDecision.MERGE:
            candidate_id = _require_candidate_id(result.candidate_transaction_id)
            candidate = await repository.lock_transaction(user_id, candidate_id)
            _validate_candidate(candidate, event, command.transaction_type)
            await ingestion.add_evidence(
                user_id,
                event.raw_event_id,
                event.id,
                candidate.id,
                locator=evidence_locator,
                excerpt=evidence_excerpt,
            )
            case = await repository.create_case(
                user_id,
                event,
                result,
                status=ReconciliationStatus.MERGED,
                resulting_transaction_id=candidate.id,
                action_type=ReconciliationActionType.AUTO_MERGED,
                from_transaction_id=None,
                evidence_locator=evidence_locator,
                evidence_excerpt=evidence_excerpt,
                score_version=SCORE_VERSION,
            )
            return ReconciliationProcessingOutcome(
                case_id=case.id,
                transaction_id=candidate.id,
                result=result,
            )

        if result.decision is ReconciliationDecision.POSSIBLE_DUPLICATE:
            case = await repository.create_case(
                user_id,
                event,
                result,
                status=ReconciliationStatus.PENDING,
                resulting_transaction_id=None,
                action_type=ReconciliationActionType.CANDIDATE_FLAGGED,
                from_transaction_id=None,
                evidence_locator=evidence_locator,
                evidence_excerpt=evidence_excerpt,
                score_version=SCORE_VERSION,
            )
            return ReconciliationProcessingOutcome(
                case_id=case.id,
                transaction_id=None,
                result=result,
            )

        transaction = await ledger.create_transaction(user_id, command)
        await ingestion.add_evidence(
            user_id,
            event.raw_event_id,
            event.id,
            transaction.id,
            locator=evidence_locator,
            excerpt=evidence_excerpt,
        )
        case = await repository.create_case(
            user_id,
            event,
            result,
            status=ReconciliationStatus.KEPT_SEPARATE,
            resulting_transaction_id=transaction.id,
            action_type=ReconciliationActionType.CREATED_NEW,
            from_transaction_id=None,
            evidence_locator=evidence_locator,
            evidence_excerpt=evidence_excerpt,
            score_version=SCORE_VERSION,
        )
        return ReconciliationProcessingOutcome(
            case_id=case.id,
            transaction_id=transaction.id,
            result=result,
        )


class ReconciliationService:
    """Owner-scoped review flow for ambiguous and previously merged events."""

    def __init__(
        self,
        database: Database,
        policy: ReconciliationPolicy,
    ) -> None:
        self._database = database
        self._policy = policy

    async def list(
        self,
        user_id: UUID,
        *,
        status: ReconciliationStatus | None = ReconciliationStatus.PENDING,
    ) -> tuple[ReconciliationCaseView, ...]:
        async with self._database.session_factory()() as session:
            return await ReconciliationRepository(session).list_views(
                user_id,
                status=status,
            )

    async def merge(
        self,
        user_id: UUID,
        case_id: UUID,
    ) -> ReconciliationCaseView:
        """Resolve one pending case by attaching evidence to its candidate."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ReconciliationRepository(session)
            await repository.acquire_user_write_lock(user_id)
            case = _require_pending(await repository.lock_case(user_id, case_id))
            candidate_id = _require_candidate_id(case.candidate_transaction_id)
            event = await repository.normalized_for_case(user_id, case)
            transaction_type = _transaction_type(event)
            candidate = await repository.lock_transaction(user_id, candidate_id)
            _validate_candidate(candidate, event, transaction_type)
            if await repository.evidence_for_case(user_id, case) is not None:
                raise ReconciliationConflictError(
                    code="RECONCILIATION_EVIDENCE_ALREADY_LINKED",
                    message="The reconciliation evidence is already linked.",
                )
            await IngestionRepository(session).add_evidence(
                user_id,
                case.raw_event_id,
                case.normalized_event_id,
                candidate.id,
                locator=dict(case.evidence_locator),
                excerpt=case.evidence_excerpt,
            )
            case.status = ReconciliationStatus.MERGED
            case.resulting_transaction_id = candidate.id
            await repository.append_action(
                user_id,
                case,
                action_type=ReconciliationActionType.USER_MERGED,
                from_transaction_id=None,
                to_transaction_id=candidate.id,
            )
            await self._complete_source(
                user_id,
                case,
                candidate.id,
                session=session,
            )
            await repository.flush()
            return _require_view(await repository.get_view(user_id, case.id))

    async def keep_separate(
        self,
        user_id: UUID,
        case_id: UUID,
    ) -> ReconciliationCaseView:
        """Resolve one pending case by creating its own canonical transaction."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ReconciliationRepository(session)
            await repository.acquire_user_write_lock(user_id)
            case = _require_pending(await repository.lock_case(user_id, case_id))
            if await repository.evidence_for_case(user_id, case) is not None:
                raise ReconciliationConflictError(
                    code="RECONCILIATION_EVIDENCE_ALREADY_LINKED",
                    message="The reconciliation evidence is already linked.",
                )
            event = await repository.normalized_for_case(user_id, case)
            command = await _transaction_command(user_id, event, session=session)
            transaction = await LedgerRepository(session).create_transaction(
                user_id,
                command,
            )
            await IngestionRepository(session).add_evidence(
                user_id,
                case.raw_event_id,
                case.normalized_event_id,
                transaction.id,
                locator=dict(case.evidence_locator),
                excerpt=case.evidence_excerpt,
            )
            case.status = ReconciliationStatus.KEPT_SEPARATE
            case.resulting_transaction_id = transaction.id
            await repository.append_action(
                user_id,
                case,
                action_type=ReconciliationActionType.USER_KEPT_SEPARATE,
                from_transaction_id=None,
                to_transaction_id=transaction.id,
            )
            await self._complete_source(
                user_id,
                case,
                transaction.id,
                session=session,
            )
            await repository.flush()
            return _require_view(await repository.get_view(user_id, case.id))

    async def unmerge(
        self,
        user_id: UUID,
        case_id: UUID,
    ) -> ReconciliationCaseView:
        """Create a separate transaction and repoint only this source's evidence."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ReconciliationRepository(session)
            await repository.acquire_user_write_lock(user_id)
            case = _require_merged(await repository.lock_case(user_id, case_id))
            evidence = await repository.evidence_for_case(user_id, case)
            if (
                evidence is None
                or case.resulting_transaction_id is None
                or evidence.transaction_id != case.resulting_transaction_id
            ):
                raise ReconciliationConflictError(
                    code="RECONCILIATION_EVIDENCE_MISMATCH",
                    message="The merged evidence no longer matches this reconciliation case.",
                )
            event = await repository.normalized_for_case(user_id, case)
            command = await _transaction_command(user_id, event, session=session)
            transaction = await LedgerRepository(session).create_transaction(
                user_id,
                command,
            )
            previous_transaction_id = evidence.transaction_id
            evidence.transaction_id = transaction.id
            case.status = ReconciliationStatus.UNMERGED
            case.resulting_transaction_id = transaction.id
            await repository.append_action(
                user_id,
                case,
                action_type=ReconciliationActionType.USER_UNMERGED,
                from_transaction_id=previous_transaction_id,
                to_transaction_id=transaction.id,
            )
            proposal = await repository.proposal_for_raw_event(
                user_id,
                case.raw_event_id,
            )
            if proposal is not None:
                proposal.transaction_id = transaction.id
            await repository.flush()
            return _require_view(await repository.get_view(user_id, case.id))

    async def _complete_source(
        self,
        user_id: UUID,
        case: ReconciliationCase,
        transaction_id: UUID,
        *,
        session: AsyncSession,
    ) -> None:
        processing = await IngestionRepository(session).get_processing(
            user_id,
            case.raw_event_id,
            for_update=True,
        )
        if processing.state is not RawEventState.NEEDS_REVIEW:
            raise ReconciliationConflictError(
                code="RECONCILIATION_SOURCE_NOT_REVIEWABLE",
                message="The source event is no longer awaiting reconciliation.",
            )
        require_state_transition(processing.state, RawEventState.PROCESSED)
        processing.state = RawEventState.PROCESSED
        processing.last_error_code = None
        proposal = await ReconciliationRepository(session).proposal_for_raw_event(
            user_id,
            case.raw_event_id,
        )
        if proposal is not None:
            if proposal.status is not ProposalStatus.RECONCILIATION_REVIEW:
                raise ReconciliationConflictError(
                    code="RECONCILIATION_PROPOSAL_NOT_REVIEWABLE",
                    message="The financial proposal is no longer awaiting reconciliation.",
                )
            proposal.status = ProposalStatus.APPROVED
            proposal.transaction_id = transaction_id


async def _transaction_command(
    user_id: UUID,
    event: NormalizedFinancialEvent,
    *,
    session: AsyncSession,
) -> CreateTransactionCommand:
    if event.amount is None or event.currency is None or event.occurred_at is None:
        raise ReconciliationConflictError(
            code="RECONCILIATION_EVENT_INCOMPLETE",
            message="The reconciliation event lacks required transaction fields.",
        )
    transaction_type = _transaction_type(event)
    ledger = LedgerRepository(session)
    category_id = None
    if event.category_hint is not None:
        category_id = await ledger.find_visible_category_id(
            user_id,
            normalize_lookup_text(event.category_hint),
        )
    return parse_create_transaction(
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


def _transaction_type(event: NormalizedFinancialEvent) -> TransactionType:
    transaction_type = _TRANSACTION_TYPES.get(event.event_kind)
    if transaction_type is None:
        raise ReconciliationConflictError(
            code="RECONCILIATION_EVENT_KIND_UNSUPPORTED",
            message="This financial event kind cannot be reconciled as a transaction.",
        )
    return transaction_type


def _validate_candidate(
    transaction: LedgerTransaction,
    event: NormalizedFinancialEvent,
    transaction_type: TransactionType,
) -> None:
    if (
        event.amount is None
        or event.currency is None
        or transaction.status is not TransactionStatus.POSTED
        or transaction.amount != event.amount
        or transaction.currency != event.currency
        or transaction.transaction_type is not transaction_type
    ):
        raise ReconciliationConflictError(
            code="RECONCILIATION_CANDIDATE_CHANGED",
            message="The candidate transaction no longer satisfies reconciliation rules.",
        )


def _require_candidate_id(value: UUID | None) -> UUID:
    if value is None:
        raise ReconciliationConflictError(
            code="RECONCILIATION_CANDIDATE_REQUIRED",
            message="This reconciliation decision has no candidate transaction.",
        )
    return value


def _require_pending(case: ReconciliationCase | None) -> ReconciliationCase:
    if case is None:
        raise ReconciliationNotFoundError(
            code="RECONCILIATION_CASE_NOT_FOUND",
            message="The reconciliation case was not found.",
        )
    if case.status is not ReconciliationStatus.PENDING:
        raise ReconciliationConflictError(
            code="RECONCILIATION_CASE_ALREADY_RESOLVED",
            message="The reconciliation case has already been resolved.",
        )
    return case


def _require_merged(case: ReconciliationCase | None) -> ReconciliationCase:
    if case is None:
        raise ReconciliationNotFoundError(
            code="RECONCILIATION_CASE_NOT_FOUND",
            message="The reconciliation case was not found.",
        )
    if case.status is not ReconciliationStatus.MERGED:
        raise ReconciliationConflictError(
            code="RECONCILIATION_CASE_NOT_MERGED",
            message="Only a currently merged reconciliation case can be unmerged.",
        )
    return case


def _require_view(value: ReconciliationCaseView | None) -> ReconciliationCaseView:
    if value is None:
        raise ReconciliationNotFoundError(
            code="RECONCILIATION_CASE_NOT_FOUND",
            message="The reconciliation case was not found.",
        )
    return value
