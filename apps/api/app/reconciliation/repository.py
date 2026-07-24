"""Owner-scoped PostgreSQL persistence for duplicate reconciliation."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import String, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.enums import (
    ProposalStatus,
    ReconciliationActionType,
    ReconciliationStatus,
    TransactionStatus,
    TransactionType,
)
from app.models import (
    Evidence,
    FinancialEventProposal,
    LedgerTransaction,
    Merchant,
    NormalizedFinancialEvent,
    RawEvent,
    ReconciliationAction,
    ReconciliationCase,
    SourceConnection,
)
from app.reconciliation.dto import (
    CandidateTransaction,
    ReconciliationActionView,
    ReconciliationCaseView,
    ReconciliationResult,
)
from app.reconciliation.errors import ReconciliationNotFoundError
from app.reconciliation.policy import ReconciliationPolicy


class ReconciliationRepository:
    """Persistence adapter requiring owner identity for every private operation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_user_write_lock(self, user_id: UUID) -> None:
        """Serialize candidate lookup and canonical writes for one owner."""
        advisory_key = int.from_bytes(user_id.bytes[:8], byteorder="big", signed=True)
        await self._session.execute(select(func.pg_advisory_xact_lock(advisory_key)))

    async def find_candidates(
        self,
        user_id: UUID,
        event: NormalizedFinancialEvent,
        transaction_type: TransactionType,
        policy: ReconciliationPolicy,
    ) -> tuple[CandidateTransaction, ...]:
        """Find bounded exact-money candidates by time or typed payment identifier."""
        if event.amount is None or event.currency is None or event.occurred_at is None:
            return ()

        window_start = event.occurred_at - policy.candidate_window
        window_end = event.occurred_at + policy.candidate_window
        temporal_statement = (
            select(LedgerTransaction.id)
            .where(
                LedgerTransaction.user_id == user_id,
                LedgerTransaction.amount == event.amount,
                LedgerTransaction.currency == event.currency,
                LedgerTransaction.transaction_type == transaction_type,
                LedgerTransaction.status == TransactionStatus.POSTED,
                LedgerTransaction.transaction_date >= window_start,
                LedgerTransaction.transaction_date <= window_end,
            )
            .order_by(
                func.abs(
                    func.extract(
                        "epoch",
                        LedgerTransaction.transaction_date - event.occurred_at,
                    )
                ),
                LedgerTransaction.id,
            )
            .limit(policy.max_candidates)
        )
        temporal_ids = list((await self._session.scalars(temporal_statement)).all())

        exact_ids: list[UUID] = []
        payment_identifiers = tuple(
            item for item in event.payment_identifiers if isinstance(item, str)
        )
        if payment_identifiers:
            overlap = NormalizedFinancialEvent.payment_identifiers.op("?|")(
                sql_cast(list(payment_identifiers), ARRAY(String()))
            )
            exact_statement = (
                select(Evidence.transaction_id)
                .join(
                    NormalizedFinancialEvent,
                    NormalizedFinancialEvent.id == Evidence.normalized_event_id,
                )
                .join(
                    LedgerTransaction,
                    LedgerTransaction.id == Evidence.transaction_id,
                )
                .where(
                    Evidence.user_id == user_id,
                    NormalizedFinancialEvent.user_id == user_id,
                    LedgerTransaction.user_id == user_id,
                    LedgerTransaction.amount == event.amount,
                    LedgerTransaction.currency == event.currency,
                    LedgerTransaction.transaction_type == transaction_type,
                    LedgerTransaction.status == TransactionStatus.POSTED,
                    overlap,
                )
                .distinct()
                .limit(policy.max_candidates)
            )
            exact_ids = list((await self._session.scalars(exact_statement)).all())

        candidate_ids = tuple(dict.fromkeys([*exact_ids, *temporal_ids]))[: policy.max_candidates]
        if not candidate_ids:
            return ()

        rows = (
            await self._session.execute(
                select(LedgerTransaction, Merchant.display_name)
                .outerjoin(Merchant, Merchant.id == LedgerTransaction.merchant_id)
                .where(
                    LedgerTransaction.id.in_(candidate_ids),
                    LedgerTransaction.user_id == user_id,
                )
            )
        ).all()
        identifiers: dict[UUID, set[str]] = defaultdict(set)
        identifier_rows = (
            await self._session.execute(
                select(
                    Evidence.transaction_id,
                    NormalizedFinancialEvent.payment_identifiers,
                )
                .join(
                    NormalizedFinancialEvent,
                    NormalizedFinancialEvent.id == Evidence.normalized_event_id,
                )
                .where(
                    Evidence.user_id == user_id,
                    Evidence.transaction_id.in_(candidate_ids),
                    NormalizedFinancialEvent.user_id == user_id,
                )
            )
        ).all()
        for transaction_id, raw_identifiers in identifier_rows:
            identifiers[transaction_id].update(
                item for item in raw_identifiers if isinstance(item, str)
            )

        by_id = {
            transaction.id: CandidateTransaction(
                id=transaction.id,
                amount=transaction.amount,
                currency=transaction.currency,
                transaction_type=transaction.transaction_type,
                description=transaction.description,
                transaction_date=transaction.transaction_date,
                merchant_name=merchant_name,
                payment_identifiers=tuple(sorted(identifiers[transaction.id])),
            )
            for transaction, merchant_name in rows
        }
        return tuple(by_id[candidate_id] for candidate_id in candidate_ids if candidate_id in by_id)

    async def lock_transaction(
        self,
        user_id: UUID,
        transaction_id: UUID,
    ) -> LedgerTransaction:
        transaction = await self._session.scalar(
            select(LedgerTransaction)
            .where(
                LedgerTransaction.id == transaction_id,
                LedgerTransaction.user_id == user_id,
            )
            .with_for_update()
        )
        if transaction is None:
            raise ReconciliationNotFoundError(
                code="RECONCILIATION_TRANSACTION_NOT_FOUND",
                message="The reconciliation transaction was not found.",
            )
        return transaction

    async def create_case(
        self,
        user_id: UUID,
        event: NormalizedFinancialEvent,
        result: ReconciliationResult,
        *,
        status: ReconciliationStatus,
        resulting_transaction_id: UUID | None,
        action_type: ReconciliationActionType,
        from_transaction_id: UUID | None,
        evidence_locator: dict[str, Any],
        evidence_excerpt: str | None,
        score_version: str,
    ) -> ReconciliationCase:
        case = ReconciliationCase(
            user_id=user_id,
            normalized_event_id=event.id,
            raw_event_id=event.raw_event_id,
            candidate_transaction_id=result.candidate_transaction_id,
            resulting_transaction_id=resulting_transaction_id,
            initial_decision=result.decision,
            status=status,
            score=result.score,
            score_version=score_version,
            reasons=list(result.reasons),
            evidence_locator=dict(evidence_locator),
            evidence_excerpt=evidence_excerpt,
        )
        self._session.add(case)
        await self._session.flush()
        await self.append_action(
            user_id,
            case,
            action_type=action_type,
            from_transaction_id=from_transaction_id,
            to_transaction_id=resulting_transaction_id,
        )
        return case

    async def append_action(
        self,
        user_id: UUID,
        case: ReconciliationCase,
        *,
        action_type: ReconciliationActionType,
        from_transaction_id: UUID | None,
        to_transaction_id: UUID | None,
    ) -> ReconciliationAction:
        action = ReconciliationAction(
            case_id=case.id,
            user_id=user_id,
            action_type=action_type,
            from_transaction_id=from_transaction_id,
            to_transaction_id=to_transaction_id,
            score=case.score,
            reasons=list(case.reasons),
        )
        self._session.add(action)
        await self._session.flush()
        return action

    async def lock_case(
        self,
        user_id: UUID,
        case_id: UUID,
    ) -> ReconciliationCase | None:
        return cast(
            ReconciliationCase | None,
            await self._session.scalar(
                select(ReconciliationCase)
                .where(
                    ReconciliationCase.id == case_id,
                    ReconciliationCase.user_id == user_id,
                )
                .with_for_update()
            ),
        )

    async def normalized_for_case(
        self,
        user_id: UUID,
        case: ReconciliationCase,
    ) -> NormalizedFinancialEvent:
        event = await self._session.scalar(
            select(NormalizedFinancialEvent).where(
                NormalizedFinancialEvent.id == case.normalized_event_id,
                NormalizedFinancialEvent.raw_event_id == case.raw_event_id,
                NormalizedFinancialEvent.user_id == user_id,
            )
        )
        if event is None:
            raise ReconciliationNotFoundError(
                code="RECONCILIATION_EVENT_NOT_FOUND",
                message="The normalized reconciliation event was not found.",
            )
        return event

    async def evidence_for_case(
        self,
        user_id: UUID,
        case: ReconciliationCase,
    ) -> Evidence | None:
        return cast(
            Evidence | None,
            await self._session.scalar(
                select(Evidence).where(
                    Evidence.normalized_event_id == case.normalized_event_id,
                    Evidence.raw_event_id == case.raw_event_id,
                    Evidence.user_id == user_id,
                )
            ),
        )

    async def proposal_for_raw_event(
        self,
        user_id: UUID,
        raw_event_id: UUID,
    ) -> FinancialEventProposal | None:
        return cast(
            FinancialEventProposal | None,
            await self._session.scalar(
                select(FinancialEventProposal)
                .where(
                    FinancialEventProposal.raw_event_id == raw_event_id,
                    FinancialEventProposal.user_id == user_id,
                    FinancialEventProposal.status.in_(
                        (
                            ProposalStatus.RECONCILIATION_REVIEW,
                            ProposalStatus.APPROVED,
                        )
                    ),
                )
                .with_for_update()
            ),
        )

    async def list_views(
        self,
        user_id: UUID,
        *,
        status: ReconciliationStatus | None,
        case_id: UUID | None = None,
        limit: int = 100,
    ) -> tuple[ReconciliationCaseView, ...]:
        candidate = aliased(LedgerTransaction)
        candidate_merchant = aliased(Merchant)
        statement = (
            select(
                ReconciliationCase,
                NormalizedFinancialEvent,
                SourceConnection.connector_type,
                candidate.description,
                candidate.transaction_date,
                candidate_merchant.display_name,
            )
            .join(
                NormalizedFinancialEvent,
                NormalizedFinancialEvent.id == ReconciliationCase.normalized_event_id,
            )
            .join(RawEvent, RawEvent.id == ReconciliationCase.raw_event_id)
            .join(
                SourceConnection,
                SourceConnection.id == RawEvent.source_connection_id,
            )
            .outerjoin(
                candidate,
                candidate.id == ReconciliationCase.candidate_transaction_id,
            )
            .outerjoin(
                candidate_merchant,
                candidate_merchant.id == candidate.merchant_id,
            )
            .where(
                ReconciliationCase.user_id == user_id,
                NormalizedFinancialEvent.user_id == user_id,
                RawEvent.user_id == user_id,
                SourceConnection.user_id == user_id,
            )
        )
        if status is not None:
            statement = statement.where(ReconciliationCase.status == status)
        if case_id is not None:
            statement = statement.where(ReconciliationCase.id == case_id)
        statement = statement.order_by(
            ReconciliationCase.created_at.desc(),
            ReconciliationCase.id.desc(),
        ).limit(limit)
        rows = (await self._session.execute(statement)).all()
        case_ids = tuple(row[0].id for row in rows)
        actions_by_case = await self._actions_by_case(user_id, case_ids)

        views: list[ReconciliationCaseView] = []
        for (
            case,
            event,
            source,
            candidate_description,
            candidate_occurred_at,
            candidate_merchant_name,
        ) in rows:
            if event.amount is None or event.currency is None or event.occurred_at is None:
                msg = "Reconciliation case references an incomplete transaction event"
                raise RuntimeError(msg)
            views.append(
                ReconciliationCaseView(
                    id=case.id,
                    normalized_event_id=event.id,
                    source=source,
                    event_kind=event.event_kind,
                    amount=event.amount,
                    currency=event.currency,
                    description=event.description,
                    occurred_at=event.occurred_at,
                    merchant_name=event.merchant_name,
                    candidate_transaction_id=case.candidate_transaction_id,
                    candidate_description=candidate_description,
                    candidate_occurred_at=candidate_occurred_at,
                    candidate_merchant_name=candidate_merchant_name,
                    resulting_transaction_id=case.resulting_transaction_id,
                    initial_decision=case.initial_decision,
                    status=case.status,
                    score=case.score,
                    score_version=case.score_version,
                    reasons=tuple(item for item in case.reasons if isinstance(item, str)),
                    created_at=case.created_at,
                    updated_at=case.updated_at,
                    actions=actions_by_case.get(case.id, ()),
                )
            )
        return tuple(views)

    async def get_view(
        self,
        user_id: UUID,
        case_id: UUID,
    ) -> ReconciliationCaseView | None:
        views = await self.list_views(
            user_id,
            status=None,
            case_id=case_id,
            limit=1,
        )
        return next((view for view in views if view.id == case_id), None)

    async def flush(self) -> None:
        await self._session.flush()

    async def _actions_by_case(
        self,
        user_id: UUID,
        case_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[ReconciliationActionView, ...]]:
        if not case_ids:
            return {}
        actions = (
            await self._session.scalars(
                select(ReconciliationAction)
                .where(
                    ReconciliationAction.user_id == user_id,
                    ReconciliationAction.case_id.in_(case_ids),
                )
                .order_by(
                    ReconciliationAction.created_at,
                    ReconciliationAction.id,
                )
            )
        ).all()
        grouped: dict[UUID, list[ReconciliationActionView]] = defaultdict(list)
        for action in actions:
            grouped[action.case_id].append(
                ReconciliationActionView(
                    id=action.id,
                    action_type=action.action_type,
                    from_transaction_id=action.from_transaction_id,
                    to_transaction_id=action.to_transaction_id,
                    score=Decimal(action.score),
                    reasons=tuple(item for item in action.reasons if isinstance(item, str)),
                    created_at=action.created_at,
                )
            )
        return {case_id: tuple(case_actions) for case_id, case_actions in grouped.items()}
