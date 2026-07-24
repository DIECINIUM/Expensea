"""Pure translations from application DTOs into the GraphQL contract."""

from decimal import Decimal

import strawberry

from app.ai.proposal_dto import FinancialEventProposalView
from app.domain.enums import (
    ProposalStatus,
    RecurrenceRule,
    RecurringPaymentStatus,
)
from app.domain.enums import (
    TransactionStatus as DomainTransactionStatus,
)
from app.domain.enums import (
    TransactionType as DomainTransactionType,
)
from app.graphql.types import (
    CategorySpendingType,
    CategoryType,
    ConnectorTypeValue,
    FinancialEventKindValue,
    FinancialEventProposalType,
    FinancialSummaryType,
    MerchantSpendingType,
    MonthlySpendingType,
    ObligationStatusValue,
    ObligationType,
    PageInfoType,
    PersonType,
    ProposalStatusValue,
    RecordedRecurringPaymentType,
    RecurrenceRuleValue,
    RecurringPaymentStatusValue,
    RecurringPaymentType,
    SettlementType,
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
    MerchantSpending,
    MonthlySpending,
    TransactionPage,
    TransactionView,
    UserView,
)
from app.ledger.obligation_dto import (
    ObligationView,
    PersonView,
    SettlementView,
)
from app.ledger.recurring_dto import (
    RecordedRecurringPaymentView,
    RecurringPaymentView,
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


def map_merchant_spending(value: MerchantSpending) -> MerchantSpendingType:
    return MerchantSpendingType(
        merchant_id=(
            strawberry.ID(str(value.merchant_id)) if value.merchant_id is not None else None
        ),
        merchant_name=value.merchant_name,
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


def map_recurring_payment(value: RecurringPaymentView) -> RecurringPaymentType:
    return RecurringPaymentType(
        id=strawberry.ID(str(value.id)),
        merchant_name=value.merchant_name,
        amount=money_string(value.amount),
        currency=value.currency,
        recurrence_rule=RecurrenceRuleValue[value.recurrence_rule.name],
        next_expected_date=value.next_expected_date,
        status=RecurringPaymentStatusValue[value.status.name],
    )


def map_recorded_recurring_payment(
    value: RecordedRecurringPaymentView,
) -> RecordedRecurringPaymentType:
    return RecordedRecurringPaymentType(
        recorded_expected_date=value.recorded_expected_date,
        transaction_id=strawberry.ID(str(value.transaction_id)),
        transaction_date=value.transaction_date,
        payment=map_recurring_payment(value.payment),
    )


def map_person(value: PersonView) -> PersonType:
    return PersonType(id=strawberry.ID(str(value.id)), name=value.name)


def map_obligation(value: ObligationView) -> ObligationType:
    return ObligationType(
        id=strawberry.ID(str(value.id)),
        person_id=strawberry.ID(str(value.person_id)),
        person_name=value.person_name,
        amount=money_string(value.amount),
        currency=value.currency,
        paid_amount=money_string(value.settled_amount),
        outstanding_amount=money_string(value.outstanding_amount),
        description=value.description,
        issued_date=value.issued_date,
        due_date=value.due_date,
        status=ObligationStatusValue[value.effective_status.name],
        transaction_id=(
            strawberry.ID(str(value.transaction_id)) if value.transaction_id is not None else None
        ),
    )


def map_settlement(value: SettlementView) -> SettlementType:
    return SettlementType(
        id=strawberry.ID(str(value.id)),
        obligation_id=strawberry.ID(str(value.obligation_id)),
        amount=money_string(value.amount),
        currency=value.currency,
        settled_at=value.settled_at,
        transaction_id=(
            strawberry.ID(str(value.transaction_id)) if value.transaction_id is not None else None
        ),
        note=value.note,
    )


def map_financial_event_proposal(
    value: FinancialEventProposalView,
) -> FinancialEventProposalType:
    return FinancialEventProposalType(
        id=strawberry.ID(str(value.id)),
        raw_event_id=strawberry.ID(str(value.raw_event_id)),
        source=ConnectorTypeValue[value.source.name],
        event_kind=FinancialEventKindValue[value.event_kind.name],
        amount=money_string(value.amount) if value.amount is not None else None,
        currency=value.currency,
        description=value.description,
        occurred_at=value.occurred_at,
        due_date=value.due_date,
        merchant_name=value.merchant_name,
        counterparty=value.counterparty,
        recurrence_rule=(
            RecurrenceRuleValue[value.recurrence_rule.name]
            if value.recurrence_rule is not None
            else None
        ),
        next_expected_date=value.next_expected_date,
        category_hint=value.category_hint,
        tags=list(value.tags),
        confidence=money_string(value.confidence),
        status=ProposalStatusValue[value.status.name],
        review_reasons=list(value.review_reasons),
        provider=value.provider,
        model=value.model,
        prompt_version=value.prompt_version,
        created_at=value.created_at,
        canonical_target_type=value.canonical_target_type,
        canonical_target_id=(
            strawberry.ID(str(value.canonical_target_id))
            if value.canonical_target_id is not None
            else None
        ),
    )


def to_domain_transaction_type(value: TransactionTypeValue) -> DomainTransactionType:
    return DomainTransactionType[value.name]


def to_domain_transaction_status(
    value: TransactionStatusValue,
) -> DomainTransactionStatus:
    return DomainTransactionStatus[value.name]


def to_domain_recurrence_rule(value: RecurrenceRuleValue) -> RecurrenceRule:
    return RecurrenceRule[value.name]


def to_domain_recurring_status(
    value: RecurringPaymentStatusValue,
) -> RecurringPaymentStatus:
    return RecurringPaymentStatus[value.name]


def to_domain_proposal_status(value: ProposalStatusValue) -> ProposalStatus:
    return ProposalStatus[value.name]
