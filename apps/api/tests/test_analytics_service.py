from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.analytics.service import AnalyticsService
from app.db.session import Database
from app.domain.enums import TransactionStatus, TransactionType
from app.ledger.commands import parse_create_transaction
from app.ledger.service import LedgerService
from app.models import Category, User

OWNER_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_ID = UUID("10000000-0000-4000-8000-000000000002")
FOOD_ID = UUID("70000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


async def _seed(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add_all(
            [
                User(
                    id=OWNER_ID,
                    email="analytics-owner@example.test",
                    name="Analytics Owner",
                    default_currency="INR",
                    timezone="Asia/Kolkata",
                ),
                User(
                    id=OTHER_ID,
                    email="analytics-other@example.test",
                    name="Other Owner",
                    default_currency="INR",
                    timezone="Asia/Kolkata",
                ),
                Category(id=FOOD_ID, name="Food", normalized_name="food"),
            ]
        )


def _command(
    amount: str,
    occurred_at: datetime,
    *,
    currency: str = "INR",
    transaction_type: TransactionType = TransactionType.EXPENSE,
    status: TransactionStatus = TransactionStatus.POSTED,
):
    return parse_create_transaction(
        amount=amount,
        currency=currency,
        transaction_type=transaction_type,
        description="Analytics fixture",
        transaction_date=occurred_at,
        category_id=FOOD_ID,
        merchant_name="Example Market",
        status=status,
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_report_respects_period_status_currency_and_owner(
    isolated_database: Database,
) -> None:
    await _seed(isolated_database)
    ledger = LedgerService(isolated_database)
    await ledger.create_transaction(
        OWNER_ID, _command("100.0000", datetime(2026, 6, 10, tzinfo=UTC))
    )
    current = await ledger.create_transaction(
        OWNER_ID, _command("200.0000", datetime(2026, 7, 10, tzinfo=UTC))
    )
    await ledger.create_transaction(
        OWNER_ID,
        _command(
            "25.0000",
            datetime(2026, 7, 11, tzinfo=UTC),
            transaction_type=TransactionType.REFUND,
        ),
    )
    await ledger.create_transaction(
        OWNER_ID,
        _command(
            "999.0000",
            datetime(2026, 7, 12, tzinfo=UTC),
            status=TransactionStatus.PENDING,
        ),
    )
    await ledger.create_transaction(
        OWNER_ID,
        _command("50.0000", datetime(2026, 7, 13, tzinfo=UTC), currency="USD"),
    )
    await ledger.create_transaction(
        OTHER_ID, _command("5000.0000", datetime(2026, 7, 14, tzinfo=UTC))
    )

    report = await AnalyticsService(isolated_database, clock=lambda: NOW).report(OWNER_ID)

    assert report.currency == "INR"
    assert report.current.spent == 175
    assert report.previous.spent == 100
    assert report.total_change == 75
    assert report.current.transaction_count == 2
    assert sum((item.change for item in report.contributions), start=0) == 75
    trend = next(item for item in report.insights if item.code == "spending_increase")
    assert current.id in trend.supporting_transaction_ids
