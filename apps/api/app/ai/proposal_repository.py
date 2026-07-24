"""Owner-scoped persistence for extracted financial-event proposals."""

from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extraction import FinancialExtractionResult
from app.ai.proposal_dto import FinancialEventProposalView, RawExtractionContext
from app.domain.enums import ProposalStatus
from app.models import (
    FinancialEventProposal,
    RawEvent,
    SourceConnection,
    User,
)


class ProposalRepository:
    """Persistence adapter requiring owner identity for every proposal query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def raw_extraction_context(
        self,
        user_id: UUID,
        raw_event_id: UUID,
    ) -> RawExtractionContext | None:
        row = (
            await self._session.execute(
                select(
                    RawEvent,
                    SourceConnection.connector_type,
                    User.timezone,
                    User.default_currency,
                )
                .join(
                    SourceConnection,
                    SourceConnection.id == RawEvent.source_connection_id,
                )
                .join(User, User.id == RawEvent.user_id)
                .where(
                    RawEvent.id == raw_event_id,
                    RawEvent.user_id == user_id,
                    SourceConnection.user_id == user_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        raw_event, connector_type, timezone, default_currency = row
        return RawExtractionContext(
            raw_event_id=raw_event.id,
            connector_type=connector_type,
            occurred_at=raw_event.occurred_at,
            payload=dict(raw_event.payload),
            timezone=timezone,
            default_currency=default_currency,
        )

    async def existing_for_prompt(
        self,
        user_id: UUID,
        raw_event_id: UUID,
        *,
        prompt_name: str,
        prompt_version: str,
        schema_version: str,
    ) -> FinancialEventProposalView | None:
        proposal_id = await self._session.scalar(
            select(FinancialEventProposal.id).where(
                FinancialEventProposal.user_id == user_id,
                FinancialEventProposal.raw_event_id == raw_event_id,
                FinancialEventProposal.prompt_name == prompt_name,
                FinancialEventProposal.prompt_version == prompt_version,
                FinancialEventProposal.schema_version == schema_version,
            )
        )
        if proposal_id is None:
            return None
        return await self.get(user_id, proposal_id)

    async def create_or_get(
        self,
        user_id: UUID,
        raw_context: RawExtractionContext,
        extraction: FinancialExtractionResult,
    ) -> FinancialEventProposalView:
        proposal_id = uuid4()
        event = extraction.event
        statement = (
            pg_insert(FinancialEventProposal)
            .values(
                id=proposal_id,
                user_id=user_id,
                raw_event_id=raw_context.raw_event_id,
                event_kind=event.event_kind,
                amount=event.amount,
                currency=event.currency,
                description=event.description,
                occurred_at=event.occurred_at,
                due_date=event.due_date,
                merchant_name=event.merchant_name,
                counterparty=event.counterparty,
                recurrence_rule=event.recurrence_rule,
                next_expected_date=event.next_expected_date,
                category_hint=event.category_hint,
                tags=list(event.tags),
                confidence=event.confidence,
                status=ProposalStatus.NEEDS_REVIEW,
                review_reasons=list(extraction.review_reasons),
                provider=extraction.telemetry.provider,
                model=extraction.telemetry.model,
                prompt_name=extraction.prompt_name,
                prompt_version=extraction.prompt_version,
                schema_version=extraction.schema_version,
                latency_ms=extraction.telemetry.latency_ms,
                input_tokens=extraction.telemetry.input_tokens,
                output_tokens=extraction.telemetry.output_tokens,
            )
            .on_conflict_do_nothing(
                constraint="uq_financial_event_proposals_raw_prompt",
            )
            .returning(FinancialEventProposal.id)
        )
        inserted_id = (await self._session.execute(statement)).scalar_one_or_none()
        selected_id = inserted_id or await self._session.scalar(
            select(FinancialEventProposal.id).where(
                FinancialEventProposal.user_id == user_id,
                FinancialEventProposal.raw_event_id == raw_context.raw_event_id,
                FinancialEventProposal.prompt_name == extraction.prompt_name,
                FinancialEventProposal.prompt_version == extraction.prompt_version,
                FinancialEventProposal.schema_version == extraction.schema_version,
            )
        )
        if selected_id is None:
            msg = "Proposal upsert did not return an owner-visible row"
            raise RuntimeError(msg)
        proposal = await self.get(user_id, selected_id)
        if proposal is None:
            msg = "Proposal disappeared after insertion"
            raise RuntimeError(msg)
        return proposal

    async def list(
        self,
        user_id: UUID,
        *,
        status: ProposalStatus | None = None,
    ) -> tuple[FinancialEventProposalView, ...]:
        statement = (
            select(FinancialEventProposal, SourceConnection.connector_type)
            .join(RawEvent, RawEvent.id == FinancialEventProposal.raw_event_id)
            .join(
                SourceConnection,
                SourceConnection.id == RawEvent.source_connection_id,
            )
            .where(
                FinancialEventProposal.user_id == user_id,
                RawEvent.user_id == user_id,
                SourceConnection.user_id == user_id,
            )
        )
        if status is not None:
            statement = statement.where(FinancialEventProposal.status == status)
        statement = statement.order_by(
            FinancialEventProposal.created_at.desc(),
            FinancialEventProposal.id.desc(),
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(_proposal_view(proposal, source) for proposal, source in rows)

    async def get(
        self,
        user_id: UUID,
        proposal_id: UUID,
    ) -> FinancialEventProposalView | None:
        row = (
            await self._session.execute(
                select(FinancialEventProposal, SourceConnection.connector_type)
                .join(RawEvent, RawEvent.id == FinancialEventProposal.raw_event_id)
                .join(
                    SourceConnection,
                    SourceConnection.id == RawEvent.source_connection_id,
                )
                .where(
                    FinancialEventProposal.id == proposal_id,
                    FinancialEventProposal.user_id == user_id,
                    RawEvent.user_id == user_id,
                    SourceConnection.user_id == user_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        proposal, source = row
        return _proposal_view(proposal, source)

    async def lock(
        self,
        user_id: UUID,
        proposal_id: UUID,
    ) -> FinancialEventProposal | None:
        return cast(
            FinancialEventProposal | None,
            await self._session.scalar(
                select(FinancialEventProposal)
                .where(
                    FinancialEventProposal.id == proposal_id,
                    FinancialEventProposal.user_id == user_id,
                )
                .with_for_update()
            ),
        )

    async def source_for_proposal(
        self,
        user_id: UUID,
        proposal: FinancialEventProposal,
    ) -> SourceConnection:
        source = await self._session.scalar(
            select(SourceConnection)
            .join(RawEvent, RawEvent.source_connection_id == SourceConnection.id)
            .where(
                RawEvent.id == proposal.raw_event_id,
                RawEvent.user_id == user_id,
                SourceConnection.user_id == user_id,
            )
        )
        if source is None:
            msg = "Proposal source was not visible to its owner"
            raise RuntimeError(msg)
        return source

    async def flush(self) -> None:
        await self._session.flush()


def proposal_view_from_model(
    proposal: FinancialEventProposal,
    source: SourceConnection,
) -> FinancialEventProposalView:
    """Project a locked proposal after a review state change."""
    return _proposal_view(proposal, source.connector_type)


def _proposal_view(
    proposal: FinancialEventProposal,
    source: object,
) -> FinancialEventProposalView:
    from app.domain.enums import ConnectorType

    if not isinstance(source, ConnectorType):
        msg = "Proposal source connector type is invalid"
        raise RuntimeError(msg)
    target_type, target_id = _canonical_target(proposal)
    return FinancialEventProposalView(
        id=proposal.id,
        raw_event_id=proposal.raw_event_id,
        source=source,
        event_kind=proposal.event_kind,
        amount=proposal.amount,
        currency=proposal.currency,
        description=proposal.description,
        occurred_at=proposal.occurred_at,
        due_date=proposal.due_date,
        merchant_name=proposal.merchant_name,
        counterparty=proposal.counterparty,
        recurrence_rule=proposal.recurrence_rule,
        next_expected_date=proposal.next_expected_date,
        category_hint=proposal.category_hint,
        tags=tuple(item for item in proposal.tags if isinstance(item, str)),
        confidence=proposal.confidence,
        status=proposal.status,
        review_reasons=tuple(item for item in proposal.review_reasons if isinstance(item, str)),
        provider=proposal.provider,
        model=proposal.model,
        prompt_version=proposal.prompt_version,
        created_at=proposal.created_at,
        canonical_target_type=target_type,
        canonical_target_id=target_id,
    )


def _canonical_target(
    proposal: FinancialEventProposal,
) -> tuple[str | None, UUID | None]:
    targets = (
        ("transaction", proposal.transaction_id),
        ("receivable", proposal.receivable_id),
        ("payable", proposal.payable_id),
        ("recurring_payment", proposal.recurring_payment_id),
    )
    return next(
        ((target_type, target_id) for target_type, target_id in targets if target_id is not None),
        (None, None),
    )
