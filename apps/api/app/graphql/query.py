"""Public system fields and authenticated deterministic ledger queries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import strawberry
from graphql import GraphQLError
from strawberry.types import Info

from app.graphql.context import GraphQLContext
from app.graphql.mappers import (
    map_category,
    map_category_spending,
    map_financial_event_proposal,
    map_merchant_spending,
    map_monthly_spending,
    map_obligation,
    map_person,
    map_recurring_payment,
    map_summary,
    map_transaction,
    map_transaction_page,
    map_user,
    to_domain_proposal_status,
)
from app.graphql.safety import require_user_id, resolve_safely
from app.graphql.types import (
    CategorySpendingType,
    CategoryType,
    FinancialEventProposalType,
    FinancialSummaryType,
    MerchantSpendingType,
    MonthlySpendingType,
    ObligationSummaryType,
    ObligationType,
    PersonType,
    ProposalStatusValue,
    RecurringPaymentType,
    RecurringSummaryType,
    TransactionConnectionType,
    TransactionType,
    UserType,
)
from app.ledger.commands import parse_currency
from app.ledger.periods import parse_timezone
from app.ledger.recurring_commands import parse_upcoming_recurring_window


@strawberry.type
class AppInfo:
    """Non-sensitive application metadata."""

    name: str
    version: str
    environment: str


@strawberry.type
class Query:
    """Operational and owner-scoped finance queries."""

    @strawberry.field
    def health(self) -> str:
        """Report GraphQL process health without probing dependencies."""
        return "ok"

    @strawberry.field
    def app_info(self, info: Info[GraphQLContext, None]) -> AppInfo:
        """Return stable metadata from the typed request context."""
        settings = info.context.settings
        return AppInfo(
            name=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env.value,
        )

    @strawberry.field
    async def me(self, info: Info[GraphQLContext, None]) -> UserType:
        user_id = require_user_id(info.context)
        value = await resolve_safely(info.context.ledger.get_user(user_id), info.context)
        return map_user(value)

    @strawberry.field
    async def financial_summary(
        self,
        info: Info[GraphQLContext, None],
        currency: str | None = None,
    ) -> FinancialSummaryType:
        user_id = require_user_id(info.context)
        value = await resolve_safely(
            info.context.ledger.financial_summary(user_id, currency=currency),
            info.context,
        )
        return map_summary(value)

    @strawberry.field
    async def spending_by_category(
        self,
        info: Info[GraphQLContext, None],
        currency: str | None = None,
    ) -> list[CategorySpendingType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.ledger.spending_by_category(user_id, currency=currency),
            info.context,
        )
        return [map_category_spending(value) for value in values]

    @strawberry.field
    async def monthly_spending(
        self,
        info: Info[GraphQLContext, None],
        months: int = 6,
        currency: str | None = None,
    ) -> list[MonthlySpendingType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.ledger.monthly_spending(
                user_id,
                currency=currency,
                months=months,
            ),
            info.context,
        )
        return [map_monthly_spending(value) for value in values]

    @strawberry.field
    async def spending_by_merchant(
        self,
        info: Info[GraphQLContext, None],
        currency: str | None = None,
    ) -> list[MerchantSpendingType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.ledger.spending_by_merchant(user_id, currency=currency),
            info.context,
        )
        return [map_merchant_spending(value) for value in values]

    @strawberry.field
    async def transactions(
        self,
        info: Info[GraphQLContext, None],
        first: int = 20,
        after: str | None = None,
    ) -> TransactionConnectionType:
        user_id = require_user_id(info.context)
        value = await resolve_safely(
            info.context.ledger.list_transactions(
                user_id,
                first=first,
                after=after,
            ),
            info.context,
        )
        return map_transaction_page(value)

    @strawberry.field
    async def transaction(
        self,
        info: Info[GraphQLContext, None],
        id: strawberry.ID,
    ) -> TransactionType:
        user_id = require_user_id(info.context)
        try:
            transaction_id = UUID(str(id))
        except ValueError as exc:
            raise GraphQLError(
                "Transaction ID must be a UUID.",
                extensions={"code": "INVALID_TRANSACTION_ID"},
            ) from exc
        value = await resolve_safely(
            info.context.ledger.get_transaction(user_id, transaction_id),
            info.context,
        )
        return map_transaction(value)

    @strawberry.field
    async def categories(
        self,
        info: Info[GraphQLContext, None],
    ) -> list[CategoryType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.ledger.list_categories(user_id),
            info.context,
        )
        return [map_category(value) for value in values]

    @strawberry.field
    async def financial_event_proposals(
        self,
        info: Info[GraphQLContext, None],
        status: ProposalStatusValue | None = ProposalStatusValue.NEEDS_REVIEW,
    ) -> list[FinancialEventProposalType]:
        """Return owner-scoped extracted proposals without raw private content."""
        user_id = require_user_id(info.context)
        values = await info.context.proposals.list(
            user_id,
            status=to_domain_proposal_status(status) if status is not None else None,
        )
        return [map_financial_event_proposal(value) for value in values]

    @strawberry.field
    async def recurring_payments(
        self,
        info: Info[GraphQLContext, None],
    ) -> list[RecurringPaymentType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.recurring.list(user_id),
            info.context,
        )
        return [map_recurring_payment(value) for value in values]

    @strawberry.field
    async def recurring_summary(
        self,
        info: Info[GraphQLContext, None],
        currency: str | None = None,
        days: int = 31,
    ) -> RecurringSummaryType:
        user_id = require_user_id(info.context)
        if days < 1 or days > 366:
            raise GraphQLError(
                "days must be between 1 and 366.",
                extensions={"code": "INVALID_DATE_WINDOW", "field": "days"},
            )
        user = await resolve_safely(
            info.context.ledger.get_user(user_id),
            info.context,
        )
        selected_currency = parse_currency(currency or user.default_currency)
        today = datetime.now(UTC).astimezone(parse_timezone(user.timezone)).date()
        window = parse_upcoming_recurring_window(
            start_date=today,
            end_date=today + timedelta(days=days),
        )
        totals = await resolve_safely(
            info.context.recurring.upcoming_totals(user_id, window),
            info.context,
        )
        selected = next(
            (item for item in totals if item.currency == selected_currency),
            None,
        )
        return RecurringSummaryType(
            currency=selected_currency,
            upcoming_amount=(
                format(selected.amount, "f")
                if selected is not None
                else format(Decimal("0.0000"), "f")
            ),
            upcoming_count=selected.payment_count if selected is not None else 0,
            window_start=window.start_date,
            window_end=window.end_date,
        )

    @strawberry.field
    async def people(
        self,
        info: Info[GraphQLContext, None],
    ) -> list[PersonType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.obligations.list_people(user_id),
            info.context,
        )
        return [map_person(value) for value in values]

    @strawberry.field
    async def receivables(
        self,
        info: Info[GraphQLContext, None],
    ) -> list[ObligationType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.obligations.list_receivables(user_id),
            info.context,
        )
        return [map_obligation(value) for value in values]

    @strawberry.field
    async def payables(
        self,
        info: Info[GraphQLContext, None],
    ) -> list[ObligationType]:
        user_id = require_user_id(info.context)
        values = await resolve_safely(
            info.context.obligations.list_payables(user_id),
            info.context,
        )
        return [map_obligation(value) for value in values]

    @strawberry.field
    async def obligation_summary(
        self,
        info: Info[GraphQLContext, None],
        currency: str | None = None,
    ) -> ObligationSummaryType:
        user_id = require_user_id(info.context)
        user = await resolve_safely(
            info.context.ledger.get_user(user_id),
            info.context,
        )
        selected_currency = parse_currency(currency or user.default_currency)
        totals = await resolve_safely(
            info.context.obligations.outstanding_totals(user_id),
            info.context,
        )
        selected = next(
            (item for item in totals if item.currency == selected_currency),
            None,
        )
        return ObligationSummaryType(
            currency=selected_currency,
            open_payables=(
                format(selected.payable, "f")
                if selected is not None
                else format(Decimal("0.0000"), "f")
            ),
            open_receivables=(
                format(selected.receivable, "f")
                if selected is not None
                else format(Decimal("0.0000"), "f")
            ),
            net_exposure=(
                format(selected.net_exposure, "f")
                if selected is not None
                else format(Decimal("0.0000"), "f")
            ),
        )
