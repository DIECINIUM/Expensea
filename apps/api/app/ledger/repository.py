"""Explicit owner-scoped persistence queries for the Phase 1 ledger."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, and_, case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import TransactionStatus, TransactionType
from app.ledger.commands import CreateCategoryCommand, CreateTransactionCommand
from app.ledger.dto import CategoryView, TransactionView, UserView
from app.ledger.pagination import TransactionCursor
from app.ledger.periods import MonthPeriod
from app.models import Category, LedgerTransaction, Merchant, User

_ZERO = Decimal("0.0000")
_SPENDING_TYPES = (
    TransactionType.EXPENSE,
    TransactionType.SHARED_EXPENSE,
    TransactionType.REFUND,
)


class LedgerRepository:
    """Persistence adapter that requires the owner key on every private query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user(self, user_id: UUID) -> UserView | None:
        """Return the requested owner profile."""
        user = await self._session.scalar(select(User).where(User.id == user_id))
        if user is None:
            return None
        return UserView(
            id=user.id,
            name=user.name,
            default_currency=user.default_currency,
            timezone=user.timezone,
        )

    async def list_categories(self, user_id: UUID) -> tuple[CategoryView, ...]:
        """Return shared system categories plus this owner's private categories."""
        statement = (
            select(Category)
            .where(or_(Category.user_id.is_(None), Category.user_id == user_id))
            .order_by(Category.name.asc(), Category.id.asc())
        )
        categories = (await self._session.scalars(statement)).all()
        return tuple(CategoryView(id=category.id, name=category.name) for category in categories)

    async def category_is_visible(self, user_id: UUID, category_id: UUID) -> bool:
        """Check category visibility without exposing another owner's record."""
        statement = select(Category.id).where(
            Category.id == category_id,
            or_(Category.user_id.is_(None), Category.user_id == user_id),
        )
        return await self._session.scalar(statement) is not None

    async def category_name_is_visible(
        self,
        user_id: UUID,
        normalized_name: str,
    ) -> bool:
        """Check for a system or private category with the same lookup key."""
        statement = select(Category.id).where(
            Category.normalized_name == normalized_name,
            or_(Category.user_id.is_(None), Category.user_id == user_id),
        )
        return await self._session.scalar(statement) is not None

    async def create_category(
        self,
        user_id: UUID,
        command: CreateCategoryCommand,
    ) -> CategoryView:
        """Insert an owner-local category."""
        category = Category(
            user_id=user_id,
            name=command.name,
            normalized_name=command.normalized_name,
            parent_category_id=command.parent_category_id,
        )
        self._session.add(category)
        await self._session.flush()
        return CategoryView(id=category.id, name=category.name)

    async def create_transaction(
        self,
        user_id: UUID,
        command: CreateTransactionCommand,
    ) -> TransactionView:
        """Insert one already-validated manual transaction."""
        merchant_id = await self._get_or_create_merchant(command)
        transaction = LedgerTransaction(
            user_id=user_id,
            amount=command.amount,
            currency=command.currency,
            transaction_type=command.transaction_type,
            description=command.description,
            transaction_date=command.transaction_date,
            status=command.status,
            category_id=command.category_id,
            merchant_id=merchant_id,
        )
        self._session.add(transaction)
        await self._session.flush()
        return await self._project_transaction(user_id, transaction.id)

    async def get_transaction(
        self,
        user_id: UUID,
        transaction_id: UUID,
    ) -> TransactionView | None:
        """Return an owner-scoped transaction projection."""
        return await self._project_transaction_or_none(user_id, transaction_id)

    async def list_transactions(
        self,
        user_id: UUID,
        *,
        limit: int,
        after: TransactionCursor | None,
    ) -> tuple[TransactionView, ...]:
        """Read a stable, descending transaction page using keyset predicates."""
        statement = (
            select(LedgerTransaction, Merchant.display_name, Category.name)
            .outerjoin(Merchant, Merchant.id == LedgerTransaction.merchant_id)
            .outerjoin(Category, Category.id == LedgerTransaction.category_id)
            .where(LedgerTransaction.user_id == user_id)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    LedgerTransaction.transaction_date < after.occurred_at,
                    and_(
                        LedgerTransaction.transaction_date == after.occurred_at,
                        LedgerTransaction.id < after.transaction_id,
                    ),
                )
            )
        statement = statement.order_by(
            LedgerTransaction.transaction_date.desc(),
            LedgerTransaction.id.desc(),
        ).limit(limit)
        rows = (await self._session.execute(statement)).all()
        return tuple(
            self._transaction_view(transaction, merchant_name, category_name)
            for transaction, merchant_name, category_name in rows
        )

    async def merchant_totals(
        self,
        user_id: UUID,
        *,
        currency: str,
        period: MonthPeriod,
    ) -> tuple[tuple[UUID | None, str, Decimal], ...]:
        """Aggregate signed spending by canonical merchant."""
        spending_expression = case(
            (
                LedgerTransaction.transaction_type.in_(
                    (TransactionType.EXPENSE, TransactionType.SHARED_EXPENSE)
                ),
                LedgerTransaction.amount,
            ),
            else_=-LedgerTransaction.amount,
        )
        statement = (
            select(
                LedgerTransaction.merchant_id,
                func.coalesce(Merchant.display_name, "No merchant"),
                func.sum(spending_expression),
            )
            .outerjoin(Merchant, Merchant.id == LedgerTransaction.merchant_id)
            .where(
                LedgerTransaction.user_id == user_id,
                LedgerTransaction.currency == currency,
                LedgerTransaction.status == TransactionStatus.POSTED,
                LedgerTransaction.transaction_type.in_(_SPENDING_TYPES),
                LedgerTransaction.transaction_date >= period.start_utc,
                LedgerTransaction.transaction_date < period.end_utc,
            )
            .group_by(LedgerTransaction.merchant_id, Merchant.display_name)
            .order_by(func.sum(spending_expression).desc(), Merchant.display_name.asc())
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(
            (merchant_id, merchant_name, Decimal(amount))
            for merchant_id, merchant_name, amount in rows
        )

    async def financial_totals(
        self,
        user_id: UUID,
        *,
        currency: str,
        period: MonthPeriod,
    ) -> tuple[Decimal, Decimal, int]:
        """Aggregate exact posted totals for one currency and UTC period."""
        spending_expression = case(
            (
                LedgerTransaction.transaction_type.in_(
                    (TransactionType.EXPENSE, TransactionType.SHARED_EXPENSE)
                ),
                LedgerTransaction.amount,
            ),
            (
                LedgerTransaction.transaction_type == TransactionType.REFUND,
                -LedgerTransaction.amount,
            ),
            else_=_ZERO,
        )
        income_expression = case(
            (
                LedgerTransaction.transaction_type == TransactionType.INCOME,
                LedgerTransaction.amount,
            ),
            else_=_ZERO,
        )
        statement = select(
            func.coalesce(func.sum(spending_expression), _ZERO),
            func.coalesce(func.sum(income_expression), _ZERO),
            func.count(LedgerTransaction.id),
        ).where(
            LedgerTransaction.user_id == user_id,
            LedgerTransaction.currency == currency,
            LedgerTransaction.status == TransactionStatus.POSTED,
            LedgerTransaction.transaction_date >= period.start_utc,
            LedgerTransaction.transaction_date < period.end_utc,
        )
        spent, income, count = (await self._session.execute(statement)).one()
        return Decimal(spent), Decimal(income), int(count)

    async def category_totals(
        self,
        user_id: UUID,
        *,
        currency: str,
        period: MonthPeriod,
    ) -> tuple[tuple[UUID | None, str, Decimal], ...]:
        """Aggregate signed spending by visible category."""
        spending_expression = case(
            (
                LedgerTransaction.transaction_type.in_(
                    (TransactionType.EXPENSE, TransactionType.SHARED_EXPENSE)
                ),
                LedgerTransaction.amount,
            ),
            else_=-LedgerTransaction.amount,
        )
        statement = (
            select(
                LedgerTransaction.category_id,
                func.coalesce(Category.name, "Uncategorized"),
                func.sum(spending_expression),
            )
            .outerjoin(Category, Category.id == LedgerTransaction.category_id)
            .where(
                LedgerTransaction.user_id == user_id,
                LedgerTransaction.currency == currency,
                LedgerTransaction.status == TransactionStatus.POSTED,
                LedgerTransaction.transaction_type.in_(_SPENDING_TYPES),
                LedgerTransaction.transaction_date >= period.start_utc,
                LedgerTransaction.transaction_date < period.end_utc,
            )
            .group_by(LedgerTransaction.category_id, Category.name)
            .order_by(func.sum(spending_expression).desc(), Category.name.asc())
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(
            (category_id, category_name, Decimal(amount))
            for category_id, category_name, amount in rows
        )

    async def monthly_totals(
        self,
        user_id: UUID,
        *,
        currency: str,
        timezone_name: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[date, Decimal]:
        """Aggregate signed spending by month in the owner's timezone."""
        local_month = cast(
            func.date_trunc(
                "month",
                func.timezone(timezone_name, LedgerTransaction.transaction_date),
            ),
            Date,
        )
        spending_expression = case(
            (
                LedgerTransaction.transaction_type.in_(
                    (TransactionType.EXPENSE, TransactionType.SHARED_EXPENSE)
                ),
                LedgerTransaction.amount,
            ),
            else_=-LedgerTransaction.amount,
        )
        statement = (
            select(local_month, func.sum(spending_expression))
            .where(
                LedgerTransaction.user_id == user_id,
                LedgerTransaction.currency == currency,
                LedgerTransaction.status == TransactionStatus.POSTED,
                LedgerTransaction.transaction_type.in_(_SPENDING_TYPES),
                LedgerTransaction.transaction_date >= start_utc,
                LedgerTransaction.transaction_date < end_utc,
            )
            .group_by(local_month)
            .order_by(local_month)
        )
        rows = (await self._session.execute(statement)).all()
        return {month_start: Decimal(amount) for month_start, amount in rows}

    async def _project_transaction(
        self,
        user_id: UUID,
        transaction_id: UUID,
    ) -> TransactionView:
        transaction = await self._project_transaction_or_none(user_id, transaction_id)
        if transaction is None:
            msg = "Inserted transaction was not visible in its owner scope"
            raise RuntimeError(msg)
        return transaction

    async def _get_or_create_merchant(
        self,
        command: CreateTransactionCommand,
    ) -> UUID | None:
        if command.merchant_name is None or command.merchant_normalized_name is None:
            return None
        statement = (
            pg_insert(Merchant)
            .values(
                display_name=command.merchant_name,
                normalized_name=command.merchant_normalized_name,
            )
            .on_conflict_do_update(
                index_elements=[Merchant.normalized_name],
                set_={"normalized_name": command.merchant_normalized_name},
            )
            .returning(Merchant.id)
        )
        return (await self._session.execute(statement)).scalar_one()

    async def _project_transaction_or_none(
        self,
        user_id: UUID,
        transaction_id: UUID,
    ) -> TransactionView | None:
        statement = (
            select(LedgerTransaction, Merchant.display_name, Category.name)
            .outerjoin(Merchant, Merchant.id == LedgerTransaction.merchant_id)
            .outerjoin(Category, Category.id == LedgerTransaction.category_id)
            .where(
                LedgerTransaction.user_id == user_id,
                LedgerTransaction.id == transaction_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        transaction, merchant_name, category_name = row
        return self._transaction_view(transaction, merchant_name, category_name)

    @staticmethod
    def _transaction_view(
        transaction: LedgerTransaction,
        merchant_name: str | None,
        category_name: str | None,
    ) -> TransactionView:
        return TransactionView(
            id=transaction.id,
            amount=transaction.amount,
            currency=transaction.currency,
            transaction_type=transaction.transaction_type,
            description=transaction.description,
            transaction_date=transaction.transaction_date,
            status=transaction.status,
            merchant_name=merchant_name,
            category_name=category_name,
        )
