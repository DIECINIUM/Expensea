"""Deterministic recurring-payment transaction boundaries."""

from calendar import monthrange
from datetime import date, timedelta
from uuid import UUID

from app.db.session import Database
from app.domain.enums import RecurrenceRule, RecurringPaymentStatus
from app.ledger.errors import LedgerConflictError, LedgerNotFoundError
from app.ledger.recurring_commands import (
    CreateRecurringPaymentCommand,
    RecordRecurringPaymentCommand,
    TransitionRecurringPaymentCommand,
    UpcomingRecurringWindow,
)
from app.ledger.recurring_dto import (
    RecordedRecurringPaymentView,
    RecurringPaymentView,
    UpcomingRecurringTotal,
)
from app.ledger.recurring_repository import (
    RecurringPaymentRepository,
    recurring_totals_for_window,
)

_STATUS_TRANSITIONS = {
    RecurringPaymentStatus.ACTIVE: frozenset(
        {
            RecurringPaymentStatus.PAUSED,
            RecurringPaymentStatus.ENDED,
        }
    ),
    RecurringPaymentStatus.PAUSED: frozenset(
        {
            RecurringPaymentStatus.ACTIVE,
            RecurringPaymentStatus.ENDED,
        }
    ),
    RecurringPaymentStatus.ENDED: frozenset(),
    RecurringPaymentStatus.NEEDS_REVIEW: frozenset(),
}


class RecurringPaymentService:
    """Owner-scoped recurring-payment use cases."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(
        self,
        user_id: UUID,
        command: CreateRecurringPaymentCommand,
    ) -> RecurringPaymentView:
        """Create one active payment and its canonical merchant atomically."""
        async with self._database.session_factory()() as session, session.begin():
            repository = RecurringPaymentRepository(session)
            await self._require_user(repository, user_id)
            merchant_id = await repository.get_or_create_merchant(command)
            return await repository.create(user_id, merchant_id, command)

    async def list(self, user_id: UUID) -> tuple[RecurringPaymentView, ...]:
        """Return all recurring payments belonging to one owner."""
        async with self._database.session_factory()() as session:
            repository = RecurringPaymentRepository(session)
            await self._require_user(repository, user_id)
            return await repository.list(user_id)

    async def get(
        self,
        user_id: UUID,
        recurring_payment_id: UUID,
    ) -> RecurringPaymentView:
        """Return one payment without revealing foreign-owner IDs."""
        async with self._database.session_factory()() as session:
            payment = await RecurringPaymentRepository(session).get(
                user_id,
                recurring_payment_id,
            )
        return self._require_payment(payment)

    async def upcoming_totals(
        self,
        user_id: UUID,
        window: UpcomingRecurringWindow,
    ) -> tuple[UpcomingRecurringTotal, ...]:
        """Return exact active totals grouped by currency."""
        async with self._database.session_factory()() as session:
            repository = RecurringPaymentRepository(session)
            await self._require_user(repository, user_id)
            rows = await repository.upcoming_totals(
                user_id,
                start_date=window.start_date,
                end_date=window.end_date,
            )
        return recurring_totals_for_window(
            rows,
            start_date=window.start_date,
            end_date=window.end_date,
        )

    async def transition_status(
        self,
        user_id: UUID,
        command: TransitionRecurringPaymentCommand,
    ) -> RecurringPaymentView:
        """Apply only explicit Phase 1 lifecycle edges."""
        async with self._database.session_factory()() as session, session.begin():
            repository = RecurringPaymentRepository(session)
            payment = self._require_payment(
                await repository.lock(user_id, command.recurring_payment_id)
            )
            if command.target_status not in _STATUS_TRANSITIONS[payment.status]:
                raise LedgerConflictError(
                    code="INVALID_RECURRING_STATUS_TRANSITION",
                    message="That recurring-payment status transition is not allowed.",
                    field="status",
                )
            return await repository.update_status(
                user_id,
                payment.id,
                command.target_status,
            )

    async def record_due_payment(
        self,
        user_id: UUID,
        command: RecordRecurringPaymentCommand,
    ) -> RecordedRecurringPaymentView:
        """Create one expense and advance its locked expected occurrence atomically."""
        async with self._database.session_factory()() as session, session.begin():
            repository = RecurringPaymentRepository(session)
            payment = self._require_payment(
                await repository.lock(user_id, command.recurring_payment_id)
            )
            if payment.status is not RecurringPaymentStatus.ACTIVE:
                raise LedgerConflictError(
                    code="RECURRING_PAYMENT_NOT_ACTIVE",
                    message="Only an active recurring payment can be recorded.",
                )
            if payment.next_expected_date != command.expected_date:
                raise LedgerConflictError(
                    code="RECURRING_OCCURRENCE_CONFLICT",
                    message="That expected occurrence is stale or was already recorded.",
                    field="expectedDate",
                )

            transaction_id = await repository.record_expense(
                user_id,
                payment,
                transaction_date=command.transaction_date,
            )
            advanced = await repository.advance(
                user_id,
                payment.id,
                advance_expected_date(
                    payment.next_expected_date,
                    payment.recurrence_rule,
                ),
            )
            return RecordedRecurringPaymentView(
                recorded_expected_date=command.expected_date,
                transaction_id=transaction_id,
                transaction_date=command.transaction_date,
                payment=advanced,
            )

    @staticmethod
    async def _require_user(
        repository: RecurringPaymentRepository,
        user_id: UUID,
    ) -> None:
        if not await repository.user_exists(user_id):
            raise LedgerNotFoundError(
                code="PROFILE_NOT_FOUND",
                message="The ledger profile was not found.",
            )

    @staticmethod
    def _require_payment(
        payment: RecurringPaymentView | None,
    ) -> RecurringPaymentView:
        if payment is None:
            raise LedgerNotFoundError(
                code="RECURRING_PAYMENT_NOT_FOUND",
                message="The recurring payment was not found.",
            )
        return payment


def advance_expected_date(current: date, rule: RecurrenceRule) -> date:
    """Advance one calendar recurrence while preserving safe month-end behavior."""
    if rule is RecurrenceRule.WEEKLY:
        return current + timedelta(days=7)
    months = {
        RecurrenceRule.MONTHLY: 1,
        RecurrenceRule.QUARTERLY: 3,
        RecurrenceRule.YEARLY: 12,
    }[rule]
    absolute_month = current.year * 12 + current.month - 1 + months
    target_year, zero_based_month = divmod(absolute_month, 12)
    target_month = zero_based_month + 1
    source_month_end = monthrange(current.year, current.month)[1]
    target_month_end = monthrange(target_year, target_month)[1]
    target_day = (
        target_month_end if current.day == source_month_end else min(current.day, target_month_end)
    )
    return date(target_year, target_month, target_day)
