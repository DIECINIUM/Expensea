"""Pure translations from application DTOs into the GraphQL contract."""

from decimal import Decimal

import strawberry

from app.domain.enums import (
    TransactionStatus as DomainTransactionStatus,
)
from app.domain.enums import (
    TransactionType as DomainTransactionType,
)
from app.graphql.types import (
    CategorySpendingType,
    CategoryType,
    FinancialSummaryType,
    MonthlySpendingType,
    PageInfoType,
    TransactionConnectionType,
    TransactionEdgeType,
    TransactionStatusValue,
    TransactionTypeValue,
    UserType,
)
from app.graphql.types import (
    TransactionType as TransactionTypeNode,
)
from app.ledger.dto import (
    CategorySpending,
    CategoryView,
    FinancialSummary,
    MonthlySpending,
    TransactionPage,
    TransactionView,
    UserView,
)


def money_string(value: Decimal) -> str:
    """Serialize exact decimal values without scientific notation."""
    return format(value, "f")


def map_user(value: UserView) -> UserType:
    return UserType(
        id=strawberry.ID(str(value.id)),
        name=value.name,
        default_currency=value.default_currency,
        timezone=value.timezone,
    )


def map_category(value: CategoryView) -> CategoryType:
    return CategoryType(id=strawberry.ID(str(value.id)), name=value.name)


def map_transaction(value: TransactionView) -> TransactionTypeNode:
    return TransactionTypeNode(
        id=strawberry.ID(str(value.id)),
        amount=money_string(value.amount),
        currency=value.currency,
        transaction_type=TransactionTypeValue[value.transaction_type.name],
        description=value.description,
        transaction_date=value.transaction_date,
        status=TransactionStatusValue[value.status.name],
        merchant_name=value.merchant_name,
        category_name=value.category_name,
    )


def map_transaction_page(value: TransactionPage) -> TransactionConnectionType:
    return TransactionConnectionType(
        edges=[
            TransactionEdgeType(cursor=edge.cursor, node=map_transaction(edge.node))
            for edge in value.edges
        ],
        page_info=PageInfoType(
            has_next_page=value.has_next_page,
            end_cursor=value.end_cursor,
        ),
    )


def map_summary(value: FinancialSummary) -> FinancialSummaryType:
    return FinancialSummaryType(
        currency=value.currency,
        period_start=value.period_start,
        period_end=value.period_end,
        spent=money_string(value.spent),
        income=money_string(value.income),
        transaction_count=value.transaction_count,
    )


def map_category_spending(value: CategorySpending) -> CategorySpendingType:
    return CategorySpendingType(
        category_id=(
            strawberry.ID(str(value.category_id)) if value.category_id is not None else None
        ),
        category_name=value.category_name,
        amount=money_string(value.amount),
        currency=value.currency,
        share_percentage=value.share_percentage,
    )


def map_monthly_spending(value: MonthlySpending) -> MonthlySpendingType:
    return MonthlySpendingType(
        month_start=value.month_start,
        amount=money_string(value.amount),
        currency=value.currency,
    )


def to_domain_transaction_type(value: TransactionTypeValue) -> DomainTransactionType:
    return DomainTransactionType[value.name]


def to_domain_transaction_status(
    value: TransactionStatusValue,
) -> DomainTransactionStatus:
    return DomainTransactionStatus[value.name]
