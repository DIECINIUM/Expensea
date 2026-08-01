"""Pure calculations for period comparison and grounded rules."""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from statistics import median
from uuid import UUID

from app.analytics.dto import (
    AnalyticsTransaction,
    CategoryContribution,
    GroundedInsight,
    OverdueReceivable,
    PeriodMetrics,
)
from app.domain.enums import TransactionType

ZERO = Decimal("0.0000")


def signed_amount(transaction: AnalyticsTransaction) -> Decimal:
    if transaction.transaction_type is TransactionType.REFUND:
        return -transaction.amount
    return transaction.amount


def period_metrics(rows: tuple[AnalyticsTransaction, ...]) -> PeriodMetrics:
    spent = sum((signed_amount(row) for row in rows), start=ZERO)
    count = len(rows)
    average = (spent / count).quantize(Decimal("0.0001")) if count else ZERO
    return PeriodMetrics(spent=spent, transaction_count=count, average_size=average)


def category_contributions(
    current: tuple[AnalyticsTransaction, ...],
    previous: tuple[AnalyticsTransaction, ...],
) -> tuple[CategoryContribution, ...]:
    grouped: dict[tuple[UUID | None, str], list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for row in current:
        grouped[(row.category_id, row.category_name)][0] += signed_amount(row)
    for row in previous:
        grouped[(row.category_id, row.category_name)][1] += signed_amount(row)
    values = [
        CategoryContribution(
            category_id=key[0],
            category_name=key[1],
            current_amount=amounts[0],
            previous_amount=amounts[1],
            change=amounts[0] - amounts[1],
        )
        for key, amounts in grouped.items()
    ]
    return tuple(sorted(values, key=lambda item: (-abs(item.change), item.category_name)))


def build_insights(
    *,
    current: tuple[AnalyticsTransaction, ...],
    history: tuple[AnalyticsTransaction, ...],
    previous_metrics: PeriodMetrics,
    current_metrics: PeriodMetrics,
    overdue: tuple[OverdueReceivable, ...],
    today: date,
) -> tuple[GroundedInsight, ...]:
    insights: list[GroundedInsight] = []
    if previous_metrics.spent > ZERO:
        percent = (
            (current_metrics.spent - previous_metrics.spent) / previous_metrics.spent * 100
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if percent >= 25:
            insights.append(
                GroundedInsight(
                    code="spending_increase",
                    title="Spending increased",
                    detail="Current-month posted spending is at least 25% above last month.",
                    amount=current_metrics.spent - previous_metrics.spent,
                    percentage=int(percent),
                    supporting_transaction_ids=tuple(row.id for row in current),
                    supporting_obligation_ids=(),
                )
            )

    positive = tuple(
        row
        for row in current
        if row.transaction_type in (TransactionType.EXPENSE, TransactionType.SHARED_EXPENSE)
    )
    if len(positive) >= 3:
        middle = Decimal(str(median([row.amount for row in positive])))
        large = tuple(row for row in positive if row.amount >= middle * 2)
        for row in large:
            insights.append(
                GroundedInsight(
                    code="large_transaction",
                    title="Large transaction",
                    detail=(
                        f"{row.merchant_name or row.category_name} is at least twice "
                        "the current median expense."
                    ),
                    amount=row.amount,
                    percentage=None,
                    supporting_transaction_ids=(row.id,),
                    supporting_obligation_ids=(),
                )
            )

    merchant_rows: dict[tuple[UUID, str], list[AnalyticsTransaction]] = defaultdict(list)
    for row in positive:
        if row.merchant_id is not None and row.merchant_name is not None:
            merchant_rows[(row.merchant_id, row.merchant_name)].append(row)
    positive_total = sum((row.amount for row in positive), start=ZERO)
    if positive_total > ZERO and merchant_rows:
        merchant, rows = max(
            merchant_rows.items(),
            key=lambda item: sum((row.amount for row in item[1]), start=ZERO),
        )
        merchant_total = sum((row.amount for row in rows), start=ZERO)
        share = int(
            (merchant_total / positive_total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if share >= 50:
            insights.append(
                GroundedInsight(
                    code="merchant_concentration",
                    title="Merchant concentration",
                    detail=f"{merchant[1]} represents at least half of positive spending.",
                    amount=merchant_total,
                    percentage=share,
                    supporting_transaction_ids=tuple(row.id for row in rows),
                    supporting_obligation_ids=(),
                )
            )

    recurring: dict[tuple[UUID, Decimal], list[AnalyticsTransaction]] = defaultdict(list)
    for row in history:
        if row.merchant_id is not None and row.transaction_type in (
            TransactionType.EXPENSE,
            TransactionType.SHARED_EXPENSE,
        ):
            recurring[(row.merchant_id, row.amount)].append(row)
    for rows in recurring.values():
        ordered = sorted(rows, key=lambda item: item.occurred_at)
        if len(ordered) < 3:
            continue
        gaps = [
            (right.occurred_at.date() - left.occurred_at.date()).days
            for left, right in pairwise(ordered)
        ]
        if gaps and all(25 <= gap <= 35 for gap in gaps):
            insights.append(
                GroundedInsight(
                    code="possible_recurring",
                    title="Possible recurring payment",
                    detail=(
                        f"{ordered[-1].merchant_name or 'A merchant'} repeated with "
                        "the same amount on a monthly cadence."
                    ),
                    amount=ordered[-1].amount,
                    percentage=None,
                    supporting_transaction_ids=tuple(row.id for row in ordered),
                    supporting_obligation_ids=(),
                )
            )

    forgotten = tuple(item for item in overdue if item.due_date < today)
    if forgotten:
        insights.append(
            GroundedInsight(
                code="forgotten_debt",
                title="Receivable may need attention",
                detail="An open receivable is past its due date.",
                amount=None,
                percentage=None,
                supporting_transaction_ids=(),
                supporting_obligation_ids=tuple(item.id for item in forgotten),
            )
        )
    return tuple(insights)
