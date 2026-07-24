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


@strawberry.enum
class RecurrenceRuleValue(Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


@strawberry.enum
class RecurringPaymentStatusValue(Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@strawberry.enum
class ObligationStatusValue(Enum):
    OPEN = "OPEN"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


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
class MerchantSpendingType:
    merchant_id: strawberry.ID | None
    merchant_name: str
    amount: str
    currency: str
    share_percentage: int


@strawberry.type
class MonthlySpendingType:
    month_start: date
    amount: str
    currency: str


@strawberry.type
class RecurringPaymentType:
    id: strawberry.ID
    merchant_name: str
    amount: str
    currency: str
    recurrence_rule: RecurrenceRuleValue
    next_expected_date: date
    status: RecurringPaymentStatusValue


@strawberry.type
class RecurringSummaryType:
    currency: str
    upcoming_amount: str
    upcoming_count: int
    window_start: date
    window_end: date


@strawberry.type
class RecordedRecurringPaymentType:
    recorded_expected_date: date
    transaction_id: strawberry.ID
    transaction_date: datetime
    payment: RecurringPaymentType


@strawberry.type
class PersonType:
    id: strawberry.ID
    name: str


@strawberry.type
class ObligationType:
    id: strawberry.ID
    person_id: strawberry.ID
    person_name: str
    amount: str
    currency: str
    paid_amount: str
    outstanding_amount: str
    description: str
    issued_date: date
    due_date: date | None
    status: ObligationStatusValue
    transaction_id: strawberry.ID | None


@strawberry.type
class SettlementType:
    id: strawberry.ID
    obligation_id: strawberry.ID
    amount: str
    currency: str
    settled_at: datetime
    transaction_id: strawberry.ID | None
    note: str | None


@strawberry.type
class ObligationSummaryType:
    currency: str
    open_payables: str
    open_receivables: str
    net_exposure: str


@strawberry.input
class CreateTransactionInput:
    amount: str
    currency: str
    transaction_type: TransactionTypeValue
    description: str
    transaction_date: datetime
    category_id: strawberry.ID | None = None
    merchant_name: str | None = None
    status: TransactionStatusValue = TransactionStatusValue.POSTED


@strawberry.input
class CreateCategoryInput:
    name: str
    parent_category_id: strawberry.ID | None = None


@strawberry.input
class CreateRecurringPaymentInput:
    merchant_name: str
    amount: str
    currency: str
    recurrence_rule: RecurrenceRuleValue
    next_expected_date: date


@strawberry.input
class CreatePersonInput:
    name: str


@strawberry.input
class CreateReceivableInput:
    person_id: strawberry.ID
    amount: str
    currency: str
    description: str
    issued_date: date
    due_date: date | None = None
    transaction_id: strawberry.ID | None = None


@strawberry.input
class CreatePayableInput:
    person_id: strawberry.ID
    amount: str
    currency: str
    description: str
    issued_date: date
    due_date: date | None = None
    transaction_id: strawberry.ID | None = None


@strawberry.input
class SettleReceivableInput:
    obligation_id: strawberry.ID
    amount: str
    settled_at: datetime
    currency: str | None = None
    transaction_id: strawberry.ID | None = None
    note: str | None = None


@strawberry.input
class SettlePayableInput:
    obligation_id: strawberry.ID
    amount: str
    settled_at: datetime
    currency: str | None = None
    transaction_id: strawberry.ID | None = None
    note: str | None = None


@strawberry.type
class CreateTransactionSuccess:
    transaction: TransactionType


@strawberry.type
class CreateCategorySuccess:
    category: CategoryType


@strawberry.type
class CreateRecurringPaymentSuccess:
    recurring_payment: RecurringPaymentType


@strawberry.type
class SetRecurringPaymentStatusSuccess:
    recurring_payment: RecurringPaymentType


@strawberry.type
class RecordRecurringPaymentSuccess:
    recorded: RecordedRecurringPaymentType


@strawberry.type
class CreatePersonSuccess:
    person: PersonType


@strawberry.type
class CreateReceivableSuccess:
    obligation: ObligationType


@strawberry.type
class CreatePayableSuccess:
    obligation: ObligationType


@strawberry.type
class SettleReceivableSuccess:
    settlement: SettlementType
    obligation: ObligationType


@strawberry.type
class SettlePayableSuccess:
    settlement: SettlementType
    obligation: ObligationType


@strawberry.type
class CancelObligationSuccess:
    obligation: ObligationType


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

CreateCategoryResult = Annotated[
    CreateCategorySuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CreateCategoryResult"),
]

CreateRecurringPaymentResult = Annotated[
    CreateRecurringPaymentSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CreateRecurringPaymentResult"),
]

SetRecurringPaymentStatusResult = Annotated[
    SetRecurringPaymentStatusSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("SetRecurringPaymentStatusResult"),
]

RecordRecurringPaymentResult = Annotated[
    RecordRecurringPaymentSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("RecordRecurringPaymentResult"),
]

CreatePersonResult = Annotated[
    CreatePersonSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CreatePersonResult"),
]

CreateReceivableResult = Annotated[
    CreateReceivableSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CreateReceivableResult"),
]

CreatePayableResult = Annotated[
    CreatePayableSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CreatePayableResult"),
]

SettleReceivableResult = Annotated[
    SettleReceivableSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("SettleReceivableResult"),
]

SettlePayableResult = Annotated[
    SettlePayableSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("SettlePayableResult"),
]

CancelObligationResult = Annotated[
    CancelObligationSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CancelObligationResult"),
]
