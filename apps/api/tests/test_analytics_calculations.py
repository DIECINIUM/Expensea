from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.analytics.calculations import (
    build_insights,
    category_contributions,
    period_metrics,
)
from app.analytics.dto import AnalyticsTransaction, OverdueReceivable
from app.domain.enums import TransactionType

FOOD_ID = UUID("70000000-0000-4000-8000-000000000001")
MERCHANT_ID = UUID("80000000-0000-4000-8000-000000000001")


def _row(
    identifier: int,
    amount: str,
    *,
    day: int,
    month: int = 7,
    transaction_type: TransactionType = TransactionType.EXPENSE,
    merchant: bool = True,
) -> AnalyticsTransaction:
    return AnalyticsTransaction(
        id=UUID(f"90000000-0000-4000-8000-{identifier:012d}"),
        amount=Decimal(amount),
        transaction_type=transaction_type,
        occurred_at=datetime(2026, month, day, 12, tzinfo=UTC),
        merchant_id=MERCHANT_ID if merchant else None,
        merchant_name="Example Market" if merchant else None,
        category_id=FOOD_ID,
        category_name="Food",
    )


def test_period_metrics_and_contributions_include_refunds_without_float_math() -> None:
    current = (
        _row(1, "100.0000", day=2),
        _row(2, "20.0000", day=3, transaction_type=TransactionType.REFUND),
    )
    previous = (_row(3, "50.0000", day=2, month=6),)

    metrics = period_metrics(current)
    contributions = category_contributions(current, previous)

    assert metrics.spent == Decimal("80.0000")
    assert metrics.transaction_count == 2
    assert metrics.average_size == Decimal("40.0000")
    assert sum((item.change for item in contributions), start=Decimal("0")) == Decimal("30.0000")


def test_zero_baseline_does_not_create_percentage_trend() -> None:
    current = (_row(1, "100.0000", day=2),)
    insights = build_insights(
        current=current,
        history=current,
        previous_metrics=period_metrics(()),
        current_metrics=period_metrics(current),
        overdue=(),
        today=date(2026, 7, 27),
    )

    assert all(item.code != "spending_increase" for item in insights)


def test_rules_are_conservative_and_ground_every_result() -> None:
    current = (
        _row(1, "100.0000", day=1),
        _row(2, "100.0000", day=5),
        _row(3, "500.0000", day=10),
    )
    history = (
        _row(4, "100.0000", day=1, month=5),
        _row(5, "100.0000", day=1, month=6),
        *current,
    )
    overdue = (
        OverdueReceivable(
            id=UUID("a0000000-0000-4000-8000-000000000001"),
            due_date=date(2026, 7, 1),
        ),
    )

    insights = build_insights(
        current=current,
        history=history,
        previous_metrics=period_metrics((_row(8, "200.0000", day=1, month=6),)),
        current_metrics=period_metrics(current),
        overdue=overdue,
        today=date(2026, 7, 27),
    )

    codes = {item.code for item in insights}
    assert {
        "spending_increase",
        "large_transaction",
        "merchant_concentration",
        "forgotten_debt",
    }.issubset(codes)
    assert all(
        item.supporting_transaction_ids or item.supporting_obligation_ids for item in insights
    )


def test_recurring_requires_three_exact_monthly_observations() -> None:
    history = (
        _row(1, "649.0000", day=1, month=5),
        _row(2, "649.0000", day=1, month=6),
        _row(3, "649.0000", day=1, month=7),
    )
    insights = build_insights(
        current=(history[-1],),
        history=history,
        previous_metrics=period_metrics(()),
        current_metrics=period_metrics((history[-1],)),
        overdue=(),
        today=date(2026, 7, 27),
    )

    recurring = next(item for item in insights if item.code == "possible_recurring")
    assert recurring.supporting_transaction_ids == tuple(row.id for row in history)
