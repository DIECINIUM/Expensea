"""Public system fields and authenticated deterministic ledger queries."""

from uuid import UUID

import strawberry
from graphql import GraphQLError
from strawberry.types import Info

from app.graphql.context import GraphQLContext
from app.graphql.mappers import (
    map_category,
    map_category_spending,
    map_monthly_spending,
    map_summary,
    map_transaction,
    map_transaction_page,
    map_user,
)
from app.graphql.safety import require_user_id, resolve_safely
from app.graphql.types import (
    CategorySpendingType,
    CategoryType,
    FinancialSummaryType,
    MonthlySpendingType,
    TransactionConnectionType,
    TransactionType,
    UserType,
)


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
