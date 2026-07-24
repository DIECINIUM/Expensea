"""Owner-scoped PostgreSQL queries for recurring-payment workflows."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Row, Select, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    RecurringPaymentStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.ledger.recurring_commands import CreateRecurringPaymentCommand
from app.ledger.recurring_dto import RecurringPaymentView, UpcomingRecurringTotal
from app.models import LedgerTransaction, Merchant, RecurringPayment, User


class RecurringPaymentRepository:
    """Persistence adapter whose private queries always require an owner key."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def user_exists(self, user_id: UUID) -> bool:
        """Return whether an owner profile exists."""
        return await self._session.scalar(select(User.id).where(User.id == user_id)) is not None

    async def get_or_create_merchant(
        self,
        command: CreateRecurringPaymentCommand,
    ) -> UUID:
        """Resolve one global canonical merchant without a check-then-insert race."""
        statement = (
            insert(Merchant)
            .values(
                normalized_name=command.normalized_merchant_name,
                display_name=command.merchant_name,
            )
            .on_conflict_do_nothing(index_elements=[Merchant.normalized_name])
            .returning(Merchant.id)
        )
        merchant_id = await self._session.scalar(statement)
        if merchant_id is not None:
            return merchant_id

        existing_id = await self._session.scalar(
            select(Merchant.id).where(
                Merchant.normalized_name == command.normalized_merchant_name,
            )
        )
        if existing_id is None:
            msg = "Canonical merchant insert completed without a visible row"
            raise RuntimeError(msg)
        return existing_id

    async def create(
        self,
        user_id: UUID,
        merchant_id: UUID,
        command: CreateRecurringPaymentCommand,
    ) -> RecurringPaymentView:
        """Insert one active manually managed recurring payment."""
        payment = RecurringPayment(
            user_id=user_id,
            merchant_id=merchant_id,
            amount=command.amount,
            currency=command.currency,
            recurrence_rule=command.recurrence_rule,
            next_expected_date=command.next_expected_date,
            status=RecurringPaymentStatus.ACTIVE,
        )
        self._session.add(payment)
        await self._session.flush()
        return await self._require_projection(user_id, payment.id)

    async def get(
        self,
        user_id: UUID,
        recurring_payment_id: UUID,
    ) -> RecurringPaymentView | None:
        """Return one payment only through its owner scope."""
        return await self._project_or_none(user_id, recurring_payment_id)

    async def lock(
        self,
        user_id: UUID,
        recurring_payment_id: UUID,
    ) -> RecurringPaymentView | None:
        """Lock one owner-scoped payment for a state-changing workflow."""
        statement = self._projection_statement(user_id, recurring_payment_id).with_for_update(
            of=RecurringPayment
        )
        row = (await self._session.execute(statement)).one_or_none()
        return self._view_from_row(row) if row is not None else None

    async def list(self, user_id: UUID) -> tuple[RecurringPaymentView, ...]:
        """Return this owner's payments in deterministic expected-date order."""
        statement = (
            select(RecurringPayment, Merchant.display_name)
            .join(Merchant, Merchant.id == RecurringPayment.merchant_id)
            .where(RecurringPayment.user_id == user_id)
            .order_by(
                RecurringPayment.next_expected_date.asc(),
                RecurringPayment.id.asc(),
            )
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(self._view_from_row(row) for row in rows)

    async def upcoming_totals(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[tuple[str, Decimal, int], ...]:
        """Aggregate active expected amounts by currency in an inclusive window."""
        statement = (
            select(
                RecurringPayment.currency,
                func.sum(RecurringPayment.amount),
                func.count(RecurringPayment.id),
            )
            .where(
                RecurringPayment.user_id == user_id,
                RecurringPayment.status == RecurringPaymentStatus.ACTIVE,
                RecurringPayment.next_expected_date >= start_date,
                RecurringPayment.next_expected_date <= end_date,
            )
            .group_by(RecurringPayment.currency)
            .order_by(RecurringPayment.currency.asc())
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(
            (currency, Decimal(amount), int(payment_count))
            for currency, amount, payment_count in rows
        )

    async def update_status(
        self,
        user_id: UUID,
        recurring_payment_id: UUID,
        status: RecurringPaymentStatus,
    ) -> RecurringPaymentView:
        """Persist a service-approved lifecycle transition."""
        await self._session.execute(
            update(RecurringPayment)
            .where(
                RecurringPayment.id == recurring_payment_id,
                RecurringPayment.user_id == user_id,
            )
            .values(status=status, updated_at=func.now())
        )
        await self._session.flush()
        return await self._require_projection(user_id, recurring_payment_id)

    async def record_expense(
        self,
        user_id: UUID,
        payment: RecurringPaymentView,
        *,
        transaction_date: datetime,
    ) -> UUID:
        """Insert the deterministic transaction for one approved occurrence."""
        transaction = LedgerTransaction(
            user_id=user_id,
            amount=payment.amount,
            currency=payment.currency,
            transaction_type=TransactionType.EXPENSE,
            merchant_id=payment.merchant_id,
            description=f"Recurring payment: {payment.merchant_name}",
            transaction_date=transaction_date,
            source=TransactionSource.MANUAL,
            status=TransactionStatus.POSTED,
        )
        self._session.add(transaction)
        await self._session.flush()
        return transaction.id

    async def advance(
        self,
        user_id: UUID,
        recurring_payment_id: UUID,
        next_expected_date: date,
    ) -> RecurringPaymentView:
        """Advance a locked payment after its expense has been inserted."""
        await self._session.execute(
            update(RecurringPayment)
            .where(
                RecurringPayment.id == recurring_payment_id,
                RecurringPayment.user_id == user_id,
            )
            .values(next_expected_date=next_expected_date, updated_at=func.now())
        )
        await self._session.flush()
        return await self._require_projection(user_id, recurring_payment_id)

    async def _require_projection(
        self,
        user_id: UUID,
        recurring_payment_id: UUID,
    ) -> RecurringPaymentView:
        payment = await self._project_or_none(user_id, recurring_payment_id)
        if payment is None:
            msg = "Recurring payment write was not visible in its owner scope"
            raise RuntimeError(msg)
        return payment

    async def _project_or_none(
        self,
        user_id: UUID,
        recurring_payment_id: UUID,
    ) -> RecurringPaymentView | None:
        row = (
            await self._session.execute(self._projection_statement(user_id, recurring_payment_id))
        ).one_or_none()
        return self._view_from_row(row) if row is not None else None

    @staticmethod
    def _projection_statement(
        user_id: UUID,
        recurring_payment_id: UUID,
    ) -> Select[tuple[RecurringPayment, str]]:
        return (
            select(RecurringPayment, Merchant.display_name)
            .join(Merchant, Merchant.id == RecurringPayment.merchant_id)
            .where(
                RecurringPayment.user_id == user_id,
                RecurringPayment.id == recurring_payment_id,
            )
        )

    @staticmethod
    def _view_from_row(
        row: Row[tuple[RecurringPayment, str]],
    ) -> RecurringPaymentView:
        payment, merchant_name = row
        return RecurringPaymentView(
            id=payment.id,
            merchant_id=payment.merchant_id,
            merchant_name=merchant_name,
            amount=payment.amount,
            currency=payment.currency,
            recurrence_rule=payment.recurrence_rule,
            next_expected_date=payment.next_expected_date,
            status=payment.status,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )


def recurring_totals_for_window(
    rows: tuple[tuple[str, Decimal, int], ...],
    *,
    start_date: date,
    end_date: date,
) -> tuple[UpcomingRecurringTotal, ...]:
    """Map persistence aggregates into owner-safe service values."""
    return tuple(
        UpcomingRecurringTotal(
            currency=currency,
            amount=amount,
            payment_count=payment_count,
            window_start=start_date,
            window_end=end_date,
        )
        for currency, amount, payment_count in rows
    )
