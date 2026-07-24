"""GraphQL-only enums and result types for the deterministic ledger."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated

import strawberry


@strawberry.enum
class TransactionTypeValue(Enum):
    """Public transaction vocabulary."""

    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"
    REFUND = "REFUND"
    SHARED_EXPENSE = "SHARED_EXPENSE"


@strawberry.enum
class TransactionStatusValue(Enum):
    """Public transaction posting lifecycle."""

    PENDING = "PENDING"
    POSTED = "POSTED"
    VOIDED = "VOIDED"


@strawberry.type
class UserType:
    id: strawberry.ID
    name: str
    default_currency: str
    timezone: str


@strawberry.type
class CategoryType:
    id: strawberry.ID
    name: str


@strawberry.type
class TransactionType:
    id: strawberry.ID
    amount: str
    currency: str
    transaction_type: TransactionTypeValue
    description: str
    transaction_date: datetime
    status: TransactionStatusValue
    merchant_name: str | None
    category_name: str | None


@strawberry.type
class TransactionEdgeType:
    cursor: str
    node: TransactionType


@strawberry.type
class PageInfoType:
    has_next_page: bool
    end_cursor: str | None


@strawberry.type
class TransactionConnectionType:
    edges: list[TransactionEdgeType]
    page_info: PageInfoType


@strawberry.type
class FinancialSummaryType:
    currency: str
    period_start: date
    period_end: date
    spent: str
    income: str
    transaction_count: int


@strawberry.type
class CategorySpendingType:
    category_id: strawberry.ID | None
    category_name: str
    amount: str
    currency: str
    share_percentage: int


@strawberry.type
class MonthlySpendingType:
    month_start: date
    amount: str
    currency: str


@strawberry.input
class CreateTransactionInput:
    amount: str
    currency: str
    transaction_type: TransactionTypeValue
    description: str
    transaction_date: datetime
    category_id: strawberry.ID | None = None
    status: TransactionStatusValue = TransactionStatusValue.POSTED


@strawberry.type
class CreateTransactionSuccess:
    transaction: TransactionType


@strawberry.interface
class ClientProblem:
    code: str
    message: str
    field: str | None


@strawberry.type
class ValidationProblem(ClientProblem):
    pass


@strawberry.type
class NotFoundProblem(ClientProblem):
    pass


@strawberry.type
class ConflictProblem(ClientProblem):
    pass


CreateTransactionResult = Annotated[
    CreateTransactionSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CreateTransactionResult"),
]
