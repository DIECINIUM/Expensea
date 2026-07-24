"""Transaction boundaries and deterministic financial calculations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.db.session import Database
from app.ledger.commands import CreateTransactionCommand, parse_currency
from app.ledger.dto import (
    CategorySpending,
    CategoryView,
    FinancialSummary,
    MonthlySpending,
    TransactionEdge,
    TransactionPage,
    TransactionView,
    UserView,
)
from app.ledger.errors import LedgerNotFoundError
from app.ledger.pagination import (
    DEFAULT_PAGE_SIZE,
    TransactionCursor,
    decode_transaction_cursor,
    encode_transaction_cursor,
    validate_page_size,
)
from app.ledger.periods import YearMonth, month_period, previous_months
from app.ledger.repository import LedgerRepository

Clock = Callable[[], datetime]
_ZERO = Decimal("0.0000")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LedgerService:
    """Owner-scoped ledger use cases backed by short-lived sessions."""

    def __init__(self, database: Database, *, clock: Clock = _utc_now) -> None:
        self._database = database
        self._clock = clock

    async def get_user(self, user_id: UUID) -> UserView:
        """Return the authenticated profile or a bounded absence error."""
        async with self._database.session_factory()() as session:
            user = await LedgerRepository(session).get_user(user_id)
        return self._require_user(user)

    async def list_categories(self, user_id: UUID) -> tuple[CategoryView, ...]:
        """Return categories available to one owner."""
        async with self._database.session_factory()() as session:
            repository = LedgerRepository(session)
            self._require_user(await repository.get_user(user_id))
            return await repository.list_categories(user_id)

    async def create_transaction(
        self,
        user_id: UUID,
        command: CreateTransactionCommand,
    ) -> TransactionView:
        """Persist one manual transaction atomically."""
        async with self._database.session_factory()() as session, session.begin():
            repository = LedgerRepository(session)
            self._require_user(await repository.get_user(user_id))
            if command.category_id is not None and not await repository.category_is_visible(
                user_id,
                command.category_id,
            ):
                raise LedgerNotFoundError(
                    code="CATEGORY_NOT_FOUND",
                    message="The selected category was not found.",
                    field="categoryId",
                )
            return await repository.create_transaction(user_id, command)

    async def get_transaction(
        self,
        user_id: UUID,
        transaction_id: UUID,
    ) -> TransactionView:
        """Return one owner-scoped transaction."""
        async with self._database.session_factory()() as session:
            transaction = await LedgerRepository(session).get_transaction(
                user_id,
                transaction_id,
            )
        if transaction is None:
            raise LedgerNotFoundError(
                code="TRANSACTION_NOT_FOUND",
                message="The transaction was not found.",
            )
        return transaction

    async def list_transactions(
        self,
        user_id: UUID,
        *,
        first: int = DEFAULT_PAGE_SIZE,
        after: str | None = None,
    ) -> TransactionPage:
        """Return a stable owner-scoped forward page."""
        page_size = validate_page_size(first)
        decoded_cursor = decode_transaction_cursor(after) if after is not None else None
        async with self._database.session_factory()() as session:
            repository = LedgerRepository(session)
            self._require_user(await repository.get_user(user_id))
            rows = await repository.list_transactions(
                user_id,
                limit=page_size + 1,
                after=decoded_cursor,
            )

        has_next_page = len(rows) > page_size
        page_rows = rows[:page_size]
        edges = tuple(
            TransactionEdge(
                cursor=encode_transaction_cursor(
                    TransactionCursor(
                        occurred_at=row.transaction_date,
                        transaction_id=row.id,
                    )
                ),
                node=row,
            )
            for row in page_rows
        )
        return TransactionPage(
            edges=edges,
            has_next_page=has_next_page,
            end_cursor=edges[-1].cursor if edges else None,
        )

    async def financial_summary(
        self,
        user_id: UUID,
        *,
        currency: str | None = None,
        month: YearMonth | None = None,
    ) -> FinancialSummary:
        """Calculate exact current-month totals without currency conversion."""
        async with self._database.session_factory()() as session:
            repository = LedgerRepository(session)
            user = self._require_user(await repository.get_user(user_id))
            selected_currency = parse_currency(currency or user.default_currency)
            selected_month = month or YearMonth.containing(self._now(), user.timezone)
            period = month_period(selected_month, user.timezone)
            spent, income, transaction_count = await repository.financial_totals(
                user_id,
                currency=selected_currency,
                period=period,
            )
        return FinancialSummary(
            currency=selected_currency,
            period_start=period.start_date,
            period_end=period.end_date,
            spent=spent,
            income=income,
            transaction_count=transaction_count,
        )

    async def spending_by_category(
        self,
        user_id: UUID,
        *,
        currency: str | None = None,
        month: YearMonth | None = None,
    ) -> tuple[CategorySpending, ...]:
        """Calculate category contributions using the summary's signed semantics."""
        async with self._database.session_factory()() as session:
            repository = LedgerRepository(session)
            user = self._require_user(await repository.get_user(user_id))
            selected_currency = parse_currency(currency or user.default_currency)
            selected_month = month or YearMonth.containing(self._now(), user.timezone)
            period = month_period(selected_month, user.timezone)
            totals = await repository.category_totals(
                user_id,
                currency=selected_currency,
                period=period,
            )

        denominator = sum((amount for _, _, amount in totals), start=_ZERO)
        return tuple(
            CategorySpending(
                category_id=category_id,
                category_name=category_name,
                amount=amount,
                currency=selected_currency,
                share_percentage=self._percentage(amount, denominator),
            )
            for category_id, category_name, amount in totals
        )

    async def monthly_spending(
        self,
        user_id: UUID,
        *,
        currency: str | None = None,
        months: int = 6,
    ) -> tuple[MonthlySpending, ...]:
        """Return an ascending, gap-filled local-month spending series."""
        async with self._database.session_factory()() as session:
            repository = LedgerRepository(session)
            user = self._require_user(await repository.get_user(user_id))
            selected_currency = parse_currency(currency or user.default_currency)
            ending_month = YearMonth.containing(self._now(), user.timezone)
            selected_months = previous_months(ending_month, months)
            periods = [month_period(item, user.timezone) for item in selected_months]
            totals = await repository.monthly_totals(
                user_id,
                currency=selected_currency,
                timezone_name=user.timezone,
                start_utc=periods[0].start_utc,
                end_utc=periods[-1].end_utc,
            )

        return tuple(
            MonthlySpending(
                month_start=period.start_date,
                amount=totals.get(period.start_date, _ZERO),
                currency=selected_currency,
            )
            for period in periods
        )

    def _now(self) -> datetime:
        instant = self._clock()
        if instant.tzinfo is None or instant.utcoffset() is None:
            msg = "Ledger clock must return a timezone-aware instant"
            raise RuntimeError(msg)
        return instant.astimezone(UTC)

    @staticmethod
    def _percentage(amount: Decimal, total: Decimal) -> int:
        if total <= 0:
            return 0
        return int(((amount / total) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _require_user(user: UserView | None) -> UserView:
        if user is None:
            raise LedgerNotFoundError(
                code="PROFILE_NOT_FOUND",
                message="The ledger profile was not found.",
            )
        return user
