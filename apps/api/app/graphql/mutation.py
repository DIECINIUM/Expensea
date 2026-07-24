"""Phase 1 GraphQL mutations."""

from datetime import date, datetime
from typing import cast
from uuid import UUID

import strawberry
from strawberry.types import Info

from app.ai.errors import AIError, ProposalReviewError
from app.graphql.context import GraphQLContext
from app.graphql.mappers import (
    map_category,
    map_financial_event_proposal,
    map_obligation,
    map_person,
    map_recorded_recurring_payment,
    map_recurring_payment,
    map_settlement,
    map_transaction,
    to_domain_recurrence_rule,
    to_domain_recurring_status,
    to_domain_transaction_status,
    to_domain_transaction_type,
)
from app.graphql.safety import require_user_id
from app.graphql.types import (
    CancelObligationResult,
    CancelObligationSuccess,
    ConflictProblem,
    CreateCategoryInput,
    CreateCategoryResult,
    CreateCategorySuccess,
    CreatePayableInput,
    CreatePayableResult,
    CreatePayableSuccess,
    CreatePersonInput,
    CreatePersonResult,
    CreatePersonSuccess,
    CreateReceivableInput,
    CreateReceivableResult,
    CreateReceivableSuccess,
    CreateRecurringPaymentInput,
    CreateRecurringPaymentResult,
    CreateRecurringPaymentSuccess,
    CreateTransactionInput,
    CreateTransactionResult,
    CreateTransactionSuccess,
    ImportGoogleKeepNoteInput,
    ImportGoogleKeepNoteResult,
    ImportGoogleKeepNoteSuccess,
    NotFoundProblem,
    RecordRecurringPaymentResult,
    RecordRecurringPaymentSuccess,
    RecurringPaymentStatusValue,
    ReviewFinancialProposalResult,
    ReviewFinancialProposalSuccess,
    SetRecurringPaymentStatusResult,
    SetRecurringPaymentStatusSuccess,
    SettlePayableInput,
    SettlePayableResult,
    SettlePayableSuccess,
    SettleReceivableInput,
    SettleReceivableResult,
    SettleReceivableSuccess,
    SubmitFinancialNoteInput,
    SubmitFinancialNoteResult,
    SubmitFinancialNoteSuccess,
    ValidationProblem,
)
from app.ingestion.errors import IngestionError
from app.ledger.commands import parse_create_category, parse_create_transaction
from app.ledger.errors import (
    LedgerConflictError,
    LedgerNotFoundError,
    LedgerValidationError,
)
from app.ledger.obligation_commands import (
    parse_create_obligation,
    parse_create_person,
    parse_settlement,
)
from app.ledger.recurring_commands import (
    parse_create_recurring_payment,
    parse_record_recurring_payment,
    parse_recurring_status_transition,
)


@strawberry.type
class Mutation:
    """Validated commands; resolvers contain no financial calculations."""

    @strawberry.mutation
    async def create_transaction(
        self,
        info: Info[GraphQLContext, None],
        input: CreateTransactionInput,
    ) -> CreateTransactionResult:
        """Persist one manual transaction for the authenticated principal."""
        user_id = require_user_id(info.context)
        try:
            category_id = UUID(str(input.category_id)) if input.category_id else None
        except ValueError:
            return ValidationProblem(
                code="INVALID_CATEGORY_ID",
                message="Category ID must be a UUID.",
                field="categoryId",
            )

        try:
            command = parse_create_transaction(
                amount=input.amount,
                currency=input.currency,
                transaction_type=to_domain_transaction_type(input.transaction_type),
                description=input.description,
                transaction_date=input.transaction_date,
                status=to_domain_transaction_status(input.status),
                category_id=category_id,
                merchant_name=input.merchant_name,
            )
            created = await info.context.ledger.create_transaction(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerNotFoundError as exc:
            return NotFoundProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerConflictError as exc:
            return ConflictProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )

        return CreateTransactionSuccess(transaction=map_transaction(created))

    @strawberry.mutation
    async def submit_financial_note(
        self,
        info: Info[GraphQLContext, None],
        input: SubmitFinancialNoteInput,
    ) -> SubmitFinancialNoteResult:
        """Extract one authenticated note into a review-only proposal."""
        user_id = require_user_id(info.context)
        try:
            client_request_id = _parse_uuid(
                input.client_request_id,
                "clientRequestId",
            )
            proposal = await info.context.proposals.submit_manual_note(
                user_id,
                note=input.note,
                source_timestamp=input.source_timestamp,
                client_request_id=client_request_id,
                labels=input.labels or (),
            )
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        except (AIError, IngestionError) as exc:
            return _proposal_problem(exc)
        return SubmitFinancialNoteSuccess(proposal=map_financial_event_proposal(proposal))

    @strawberry.mutation
    async def import_google_keep_note(
        self,
        info: Info[GraphQLContext, None],
        input: ImportGoogleKeepNoteInput,
    ) -> ImportGoogleKeepNoteResult:
        """Import one user-selected Google Keep Takeout JSON note."""
        user_id = require_user_id(info.context)
        try:
            proposal = await info.context.proposals.submit_google_keep_document(
                user_id,
                filename=input.filename,
                content=input.content,
            )
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        except (AIError, IngestionError) as exc:
            return _proposal_problem(exc)
        return ImportGoogleKeepNoteSuccess(
            proposal=(map_financial_event_proposal(proposal) if proposal is not None else None),
            ignored=proposal is None,
        )

    @strawberry.mutation
    async def approve_financial_proposal(
        self,
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
    ) -> ReviewFinancialProposalResult:
        user_id = require_user_id(info.context)
        try:
            proposal_id = _parse_uuid(id, "id")
            proposal = await info.context.proposals.approve(user_id, proposal_id)
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        except (AIError, IngestionError) as exc:
            return _proposal_problem(exc)
        return ReviewFinancialProposalSuccess(proposal=map_financial_event_proposal(proposal))

    @strawberry.mutation
    async def reject_financial_proposal(
        self,
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
    ) -> ReviewFinancialProposalResult:
        user_id = require_user_id(info.context)
        try:
            proposal_id = _parse_uuid(id, "id")
            proposal = await info.context.proposals.reject(user_id, proposal_id)
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        except (AIError, IngestionError) as exc:
            return _proposal_problem(exc)
        return ReviewFinancialProposalSuccess(proposal=map_financial_event_proposal(proposal))

    @strawberry.mutation
    async def create_category(
        self,
        info: Info[GraphQLContext, None],
        input: CreateCategoryInput,
    ) -> CreateCategoryResult:
        """Create a private category for the authenticated principal."""
        user_id = require_user_id(info.context)
        try:
            parent_id = (
                UUID(str(input.parent_category_id))
                if input.parent_category_id is not None
                else None
            )
        except ValueError:
            return ValidationProblem(
                code="INVALID_PARENT_CATEGORY_ID",
                message="Parent category ID must be a UUID.",
                field="parentCategoryId",
            )

        try:
            command = parse_create_category(
                name=input.name,
                parent_category_id=parent_id,
            )
            created = await info.context.ledger.create_category(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerNotFoundError as exc:
            return NotFoundProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerConflictError as exc:
            return ConflictProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        return CreateCategorySuccess(category=map_category(created))

    @strawberry.mutation
    async def create_recurring_payment(
        self,
        info: Info[GraphQLContext, None],
        input: CreateRecurringPaymentInput,
    ) -> CreateRecurringPaymentResult:
        user_id = require_user_id(info.context)
        try:
            command = parse_create_recurring_payment(
                amount=input.amount,
                currency=input.currency,
                merchant_name=input.merchant_name,
                recurrence_rule=to_domain_recurrence_rule(input.recurrence_rule),
                next_expected_date=input.next_expected_date,
            )
            created = await info.context.recurring.create(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        return CreateRecurringPaymentSuccess(recurring_payment=map_recurring_payment(created))

    @strawberry.mutation
    async def set_recurring_payment_status(
        self,
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
        status: RecurringPaymentStatusValue,
    ) -> SetRecurringPaymentStatusResult:
        user_id = require_user_id(info.context)
        try:
            payment_id = UUID(str(id))
        except ValueError:
            return ValidationProblem(
                code="INVALID_RECURRING_PAYMENT_ID",
                message="Recurring payment ID must be a UUID.",
                field="id",
            )
        try:
            command = parse_recurring_status_transition(
                recurring_payment_id=payment_id,
                target_status=to_domain_recurring_status(status),
            )
            updated = await info.context.recurring.transition_status(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        return SetRecurringPaymentStatusSuccess(recurring_payment=map_recurring_payment(updated))

    @strawberry.mutation
    async def record_recurring_payment(
        self,
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
        expected_date: date,
        transaction_date: datetime,
    ) -> RecordRecurringPaymentResult:
        user_id = require_user_id(info.context)
        try:
            payment_id = UUID(str(id))
        except ValueError:
            return ValidationProblem(
                code="INVALID_RECURRING_PAYMENT_ID",
                message="Recurring payment ID must be a UUID.",
                field="id",
            )
        try:
            command = parse_record_recurring_payment(
                recurring_payment_id=payment_id,
                expected_date=expected_date,
                transaction_date=transaction_date,
            )
            recorded = await info.context.recurring.record_due_payment(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        return RecordRecurringPaymentSuccess(recorded=map_recorded_recurring_payment(recorded))

    @strawberry.mutation
    async def create_person(
        self,
        info: Info[GraphQLContext, None],
        input: CreatePersonInput,
    ) -> CreatePersonResult:
        user_id = require_user_id(info.context)
        try:
            command = parse_create_person(name=input.name)
            created = await info.context.obligations.create_person(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        return CreatePersonSuccess(person=map_person(created))

    @strawberry.mutation
    async def create_receivable(
        self,
        info: Info[GraphQLContext, None],
        input: CreateReceivableInput,
    ) -> CreateReceivableResult:
        return cast(
            CreateReceivableResult,
            await Mutation._create_obligation(info, input, receivable=True),
        )

    @strawberry.mutation
    async def create_payable(
        self,
        info: Info[GraphQLContext, None],
        input: CreatePayableInput,
    ) -> CreatePayableResult:
        return cast(
            CreatePayableResult,
            await Mutation._create_obligation(info, input, receivable=False),
        )

    @strawberry.mutation
    async def settle_receivable(
        self,
        info: Info[GraphQLContext, None],
        input: SettleReceivableInput,
    ) -> SettleReceivableResult:
        return cast(
            SettleReceivableResult,
            await Mutation._settle_obligation(info, input, receivable=True),
        )

    @strawberry.mutation
    async def settle_payable(
        self,
        info: Info[GraphQLContext, None],
        input: SettlePayableInput,
    ) -> SettlePayableResult:
        return cast(
            SettlePayableResult,
            await Mutation._settle_obligation(info, input, receivable=False),
        )

    @strawberry.mutation
    async def cancel_receivable(
        self,
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
    ) -> CancelObligationResult:
        return await Mutation._cancel_obligation(info, id, receivable=True)

    @strawberry.mutation
    async def cancel_payable(
        self,
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
    ) -> CancelObligationResult:
        return await Mutation._cancel_obligation(info, id, receivable=False)

    @staticmethod
    async def _create_obligation(
        info: Info[GraphQLContext, None],
        input: CreateReceivableInput | CreatePayableInput,
        *,
        receivable: bool,
    ) -> (
        CreateReceivableSuccess
        | CreatePayableSuccess
        | ValidationProblem
        | NotFoundProblem
        | ConflictProblem
    ):
        user_id = require_user_id(info.context)
        try:
            person_id = _parse_uuid(input.person_id, "personId")
            transaction_id = (
                _parse_uuid(input.transaction_id, "transactionId")
                if input.transaction_id is not None
                else None
            )
            command = parse_create_obligation(
                person_id=person_id,
                amount=input.amount,
                currency=input.currency,
                description=input.description,
                issued_date=input.issued_date,
                due_date=input.due_date,
                transaction_id=transaction_id,
            )
            created = (
                await info.context.obligations.create_receivable(user_id, command)
                if receivable
                else await info.context.obligations.create_payable(user_id, command)
            )
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        mapped = map_obligation(created)
        return (
            CreateReceivableSuccess(obligation=mapped)
            if receivable
            else CreatePayableSuccess(obligation=mapped)
        )

    @staticmethod
    async def _settle_obligation(
        info: Info[GraphQLContext, None],
        input: SettleReceivableInput | SettlePayableInput,
        *,
        receivable: bool,
    ) -> (
        SettleReceivableSuccess
        | SettlePayableSuccess
        | ValidationProblem
        | NotFoundProblem
        | ConflictProblem
    ):
        user_id = require_user_id(info.context)
        try:
            obligation_id = _parse_uuid(input.obligation_id, "obligationId")
            current = (
                await info.context.obligations.get_receivable(user_id, obligation_id)
                if receivable
                else await info.context.obligations.get_payable(user_id, obligation_id)
            )
            transaction_id = (
                _parse_uuid(input.transaction_id, "transactionId")
                if input.transaction_id is not None
                else None
            )
            command = parse_settlement(
                amount=input.amount,
                currency=input.currency or current.currency,
                settled_at=input.settled_at,
                transaction_id=transaction_id,
                note=input.note,
            )
            result = (
                await info.context.obligations.settle_receivable(
                    user_id,
                    obligation_id,
                    command,
                )
                if receivable
                else await info.context.obligations.settle_payable(
                    user_id,
                    obligation_id,
                    command,
                )
            )
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        mapped_settlement = map_settlement(result.settlement)
        mapped_obligation = map_obligation(result.obligation)
        return (
            SettleReceivableSuccess(
                settlement=mapped_settlement,
                obligation=mapped_obligation,
            )
            if receivable
            else SettlePayableSuccess(
                settlement=mapped_settlement,
                obligation=mapped_obligation,
            )
        )

    @staticmethod
    async def _cancel_obligation(
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
        *,
        receivable: bool,
    ) -> CancelObligationResult:
        user_id = require_user_id(info.context)
        try:
            obligation_id = _parse_uuid(id, "id")
            cancelled = (
                await info.context.obligations.cancel_receivable(
                    user_id,
                    obligation_id,
                )
                if receivable
                else await info.context.obligations.cancel_payable(
                    user_id,
                    obligation_id,
                )
            )
        except LedgerValidationError as exc:
            return ValidationProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerNotFoundError as exc:
            return NotFoundProblem(code=exc.code, message=exc.message, field=exc.field)
        except LedgerConflictError as exc:
            return ConflictProblem(code=exc.code, message=exc.message, field=exc.field)
        return CancelObligationSuccess(obligation=map_obligation(cancelled))


def _parse_uuid(value: strawberry.ID, field: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError:
        raise LedgerValidationError(
            code="INVALID_ID",
            message="ID must be a UUID.",
            field=field,
        ) from None


def _proposal_problem(
    error: AIError | IngestionError,
) -> ValidationProblem | NotFoundProblem | ConflictProblem:
    if isinstance(error, ProposalReviewError):
        if error.code.endswith("_NOT_FOUND"):
            return NotFoundProblem(
                code=error.code,
                message=error.message,
                field=None,
            )
        if error.code in {
            "PROPOSAL_ALREADY_REVIEWED",
            "PROPOSAL_KIND_NOT_APPROVABLE",
        }:
            return ConflictProblem(
                code=error.code,
                message=error.message,
                field=None,
            )
    if error.code in {
        "SOURCE_IDENTITY_CONTENT_MISMATCH",
        "SOURCE_CONNECTION_INACTIVE",
    }:
        return ConflictProblem(code=error.code, message=error.message, field=None)
    return ValidationProblem(code=error.code, message=error.message, field=None)
