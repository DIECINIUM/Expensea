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


@strawberry.enum
class FinancialEventKindValue(Enum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"
    REFUND = "REFUND"
    SHARED_EXPENSE = "SHARED_EXPENSE"
    RECEIVABLE = "RECEIVABLE"
    PAYABLE = "PAYABLE"
    RECURRING = "RECURRING"
    UNKNOWN = "UNKNOWN"


@strawberry.enum
class ProposalStatusValue(Enum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    RECONCILIATION_REVIEW = "RECONCILIATION_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@strawberry.enum
class ReconciliationDecisionValue(Enum):
    MERGE = "MERGE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    NEW_TRANSACTION = "NEW_TRANSACTION"


@strawberry.enum
class ReconciliationStatusValue(Enum):
    PENDING = "PENDING"
    MERGED = "MERGED"
    KEPT_SEPARATE = "KEPT_SEPARATE"
    UNMERGED = "UNMERGED"


@strawberry.enum
class ReconciliationActionTypeValue(Enum):
    CANDIDATE_FLAGGED = "CANDIDATE_FLAGGED"
    AUTO_MERGED = "AUTO_MERGED"
    CREATED_NEW = "CREATED_NEW"
    USER_MERGED = "USER_MERGED"
    USER_KEPT_SEPARATE = "USER_KEPT_SEPARATE"
    USER_UNMERGED = "USER_UNMERGED"


@strawberry.enum
class ConnectorTypeValue(Enum):
    MANUAL_NOTE = "MANUAL_NOTE"
    CSV_IMPORT = "CSV_IMPORT"
    MOCK_RECEIPT = "MOCK_RECEIPT"
    GMAIL = "GMAIL"
    GOOGLE_KEEP_TAKEOUT = "GOOGLE_KEEP_TAKEOUT"


@strawberry.enum
class CategorizationSourceValue(Enum):
    USER_RULE = "USER_RULE"
    MERCHANT_MAP = "MERCHANT_MAP"
    VERIFIED_CORRECTION = "VERIFIED_CORRECTION"
    RETRIEVAL = "RETRIEVAL"
    MODEL = "MODEL"
    USER_OVERRIDE = "USER_OVERRIDE"


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
    category_source: CategorizationSourceValue | None
    category_classifier_version: str | None
    category_confidence: str | None
    category_overridden: bool


@strawberry.type
class UserCorrectionType:
    id: strawberry.ID
    transaction_id: strawberry.ID
    previous_category_name: str | None
    corrected_category_name: str
    classifier_version: str
    confidence: str
    created_at: datetime


@strawberry.type
class CategoryRuleType:
    id: strawberry.ID
    pattern: str
    category_id: strawberry.ID
    category_name: str
    priority: int
    enabled: bool


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


@strawberry.type
class FinancialEventProposalType:
    id: strawberry.ID
    raw_event_id: strawberry.ID
    source: ConnectorTypeValue
    event_kind: FinancialEventKindValue
    amount: str | None
    currency: str | None
    description: str
    occurred_at: datetime | None
    due_date: date | None
    merchant_name: str | None
    counterparty: str | None
    recurrence_rule: RecurrenceRuleValue | None
    next_expected_date: date | None
    category_hint: str | None
    tags: list[str]
    confidence: str
    status: ProposalStatusValue
    review_reasons: list[str]
    provider: str
    model: str
    prompt_version: str
    created_at: datetime
    canonical_target_type: str | None
    canonical_target_id: strawberry.ID | None


@strawberry.type
class ReconciliationActionType:
    id: strawberry.ID
    action_type: ReconciliationActionTypeValue
    from_transaction_id: strawberry.ID | None
    to_transaction_id: strawberry.ID | None
    score: str
    reasons: list[str]
    created_at: datetime


@strawberry.type
class ReconciliationCaseType:
    id: strawberry.ID
    normalized_event_id: strawberry.ID
    source: ConnectorTypeValue
    event_kind: FinancialEventKindValue
    amount: str
    currency: str
    description: str
    occurred_at: datetime
    merchant_name: str | None
    candidate_transaction_id: strawberry.ID | None
    candidate_description: str | None
    candidate_occurred_at: datetime | None
    candidate_merchant_name: str | None
    resulting_transaction_id: strawberry.ID | None
    initial_decision: ReconciliationDecisionValue
    status: ReconciliationStatusValue
    score: str
    score_version: str
    reasons: list[str]
    created_at: datetime
    updated_at: datetime
    can_unmerge: bool
    actions: list[ReconciliationActionType]


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
class CorrectTransactionCategoryInput:
    transaction_id: strawberry.ID
    category_id: strawberry.ID


@strawberry.input
class CreateCategoryRuleInput:
    pattern: str
    category_id: strawberry.ID
    priority: int = 100


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


@strawberry.input
class SubmitFinancialNoteInput:
    note: str
    source_timestamp: datetime
    client_request_id: strawberry.ID
    labels: list[str] | None = None


@strawberry.input
class ImportGoogleKeepNoteInput:
    filename: str
    content: str


@strawberry.type
class CreateTransactionSuccess:
    transaction: TransactionType


@strawberry.type
class CreateCategorySuccess:
    category: CategoryType


@strawberry.type
class CorrectTransactionCategorySuccess:
    correction: UserCorrectionType


@strawberry.type
class CreateCategoryRuleSuccess:
    rule: CategoryRuleType


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


@strawberry.type
class SubmitFinancialNoteSuccess:
    proposal: FinancialEventProposalType


@strawberry.type
class ImportGoogleKeepNoteSuccess:
    proposal: FinancialEventProposalType | None
    ignored: bool


@strawberry.type
class ReviewFinancialProposalSuccess:
    proposal: FinancialEventProposalType


@strawberry.type
class ReviewReconciliationCaseSuccess:
    case: ReconciliationCaseType


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

CorrectTransactionCategoryResult = Annotated[
    CorrectTransactionCategorySuccess | ValidationProblem | NotFoundProblem,
    strawberry.union("CorrectTransactionCategoryResult"),
]

CreateCategoryRuleResult = Annotated[
    CreateCategoryRuleSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("CreateCategoryRuleResult"),
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

SubmitFinancialNoteResult = Annotated[
    SubmitFinancialNoteSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("SubmitFinancialNoteResult"),
]

ImportGoogleKeepNoteResult = Annotated[
    ImportGoogleKeepNoteSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("ImportGoogleKeepNoteResult"),
]

ReviewFinancialProposalResult = Annotated[
    ReviewFinancialProposalSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("ReviewFinancialProposalResult"),
]

ReviewReconciliationCaseResult = Annotated[
    ReviewReconciliationCaseSuccess | ValidationProblem | NotFoundProblem | ConflictProblem,
    strawberry.union("ReviewReconciliationCaseResult"),
]
