"""Only these typed read methods are available to the agent workflow."""

from typing import Protocol
from uuid import UUID

from app.analytics.dto import AnalyticsReport
from app.ledger.dto import FinancialSummary, TransactionPage, TransactionView, UserView
from app.ledger.obligation_dto import ObligationView, OutstandingByCurrency
from app.ledger.periods import YearMonth
from app.ledger.recurring_commands import UpcomingRecurringWindow
from app.ledger.recurring_dto import UpcomingRecurringTotal


class LedgerReadTools(Protocol):
    async def financial_summary(
        self, user_id: UUID, *, currency: str | None = None, month: YearMonth | None = None
    ) -> FinancialSummary: ...

    async def list_transactions(
        self, user_id: UUID, *, first: int = 20, after: str | None = None
    ) -> TransactionPage: ...

    async def get_transaction(self, user_id: UUID, transaction_id: UUID) -> TransactionView: ...

    async def get_user(self, user_id: UUID) -> UserView: ...


class AnalyticsReadTools(Protocol):
    async def report(self, user_id: UUID, *, currency: str | None = None) -> AnalyticsReport: ...


class ObligationReadTools(Protocol):
    async def outstanding_totals(self, user_id: UUID) -> tuple[OutstandingByCurrency, ...]: ...

    async def list_receivables(self, user_id: UUID) -> tuple[ObligationView, ...]: ...

    async def list_payables(self, user_id: UUID) -> tuple[ObligationView, ...]: ...


class RecurringReadTools(Protocol):
    async def upcoming_totals(
        self, user_id: UUID, window: UpcomingRecurringWindow
    ) -> tuple[UpcomingRecurringTotal, ...]: ...
