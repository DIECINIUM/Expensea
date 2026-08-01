from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.analytics.calculations import (
    build_insights,
    category_contributions,
    period_metrics,
)
from app.analytics.dto import AnalyticsReport
from app.analytics.repository import AnalyticsRepository
from app.db.session import Database
from app.ledger.commands import parse_currency
from app.ledger.periods import YearMonth, month_period, parse_timezone
from app.ledger.repository import LedgerRepository

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AnalyticsService:
    def __init__(self, database: Database, *, clock: Clock = _utc_now) -> None:
        self._database = database
        self._clock = clock

    async def report(
        self,
        user_id: UUID,
        *,
        currency: str | None = None,
    ) -> AnalyticsReport:
        async with self._database.session_factory()() as session:
            ledger = LedgerRepository(session)
            user = await ledger.get_user(user_id)
            if user is None:
                from app.ledger.errors import LedgerNotFoundError

                raise LedgerNotFoundError(
                    code="PROFILE_NOT_FOUND",
                    message="The ledger profile was not found.",
                )
            selected_currency = parse_currency(currency or user.default_currency)
            current_month = YearMonth.containing(self._clock(), user.timezone)
            previous_month = current_month.previous()
            history_month = current_month
            for _ in range(11):
                history_month = history_month.previous()
            current_period = month_period(current_month, user.timezone)
            previous_period = month_period(previous_month, user.timezone)
            history_period = month_period(history_month, user.timezone)
            repository = AnalyticsRepository(session)
            current = await repository.transactions(
                user_id,
                currency=selected_currency,
                start_utc=current_period.start_utc,
                end_utc=current_period.end_utc,
            )
            previous = await repository.transactions(
                user_id,
                currency=selected_currency,
                start_utc=previous_period.start_utc,
                end_utc=previous_period.end_utc,
            )
            history = await repository.transactions(
                user_id,
                currency=selected_currency,
                start_utc=history_period.start_utc,
                end_utc=current_period.end_utc,
            )
            today = self._clock().astimezone(parse_timezone(user.timezone)).date()
            overdue = await repository.overdue_receivables(
                user_id,
                currency=selected_currency,
                today=today,
            )

        current_metrics = period_metrics(current)
        previous_metrics = period_metrics(previous)
        return AnalyticsReport(
            currency=selected_currency,
            current_period_start=current_period.start_date,
            current_period_end=current_period.end_date,
            previous_period_start=previous_period.start_date,
            previous_period_end=previous_period.end_date,
            current=current_metrics,
            previous=previous_metrics,
            total_change=current_metrics.spent - previous_metrics.spent,
            count_change=current_metrics.transaction_count - previous_metrics.transaction_count,
            average_size_change=current_metrics.average_size - previous_metrics.average_size,
            contributions=category_contributions(current, previous),
            insights=build_insights(
                current=current,
                history=history,
                previous_metrics=previous_metrics,
                current_metrics=current_metrics,
                overdue=overdue,
                today=today,
            ),
        )
