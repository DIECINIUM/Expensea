from datetime import date, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.dto import AnalyticsTransaction, OverdueReceivable
from app.domain.enums import ObligationStatus, TransactionStatus, TransactionType
from app.models import Category, LedgerTransaction, Merchant, Receivable

SPENDING_TYPES = (
    TransactionType.EXPENSE,
    TransactionType.SHARED_EXPENSE,
    TransactionType.REFUND,
)


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def transactions(
        self,
        user_id: UUID,
        *,
        currency: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[AnalyticsTransaction, ...]:
        rows = (
            await self._session.execute(
                select(
                    LedgerTransaction,
                    Merchant.display_name,
                    Category.name,
                )
                .outerjoin(Merchant, Merchant.id == LedgerTransaction.merchant_id)
                .outerjoin(Category, Category.id == LedgerTransaction.category_id)
                .where(
                    LedgerTransaction.user_id == user_id,
                    LedgerTransaction.currency == currency,
                    LedgerTransaction.status == TransactionStatus.POSTED,
                    LedgerTransaction.transaction_type.in_(SPENDING_TYPES),
                    LedgerTransaction.transaction_date >= start_utc,
                    LedgerTransaction.transaction_date < end_utc,
                )
                .order_by(
                    LedgerTransaction.transaction_date,
                    LedgerTransaction.id,
                )
            )
        ).all()
        return tuple(
            AnalyticsTransaction(
                id=transaction.id,
                amount=transaction.amount,
                transaction_type=transaction.transaction_type,
                occurred_at=transaction.transaction_date,
                merchant_id=transaction.merchant_id,
                merchant_name=merchant_name,
                category_id=transaction.category_id,
                category_name=category_name or "Uncategorized",
            )
            for transaction, merchant_name, category_name in rows
        )

    async def overdue_receivables(
        self,
        user_id: UUID,
        *,
        currency: str,
        today: date,
    ) -> tuple[OverdueReceivable, ...]:
        rows = (
            await self._session.execute(
                select(Receivable.id, Receivable.due_date).where(
                    Receivable.user_id == user_id,
                    Receivable.currency == currency,
                    Receivable.due_date.is_not(None),
                    Receivable.due_date < today,
                    or_(
                        Receivable.status == ObligationStatus.OPEN,
                        Receivable.status == ObligationStatus.PARTIALLY_PAID,
                    ),
                )
            )
        ).all()
        return tuple(
            OverdueReceivable(id=identifier, due_date=due_date)
            for identifier, due_date in rows
            if due_date is not None
        )
