"""PostgreSQL integration tests for tenant-safe ledger services."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.db.session import Database
from app.domain.enums import TransactionStatus, TransactionType
from app.ledger.commands import parse_create_transaction
from app.ledger.errors import LedgerNotFoundError
from app.ledger.service import LedgerService
from app.models import Category, LedgerTransaction, User

OWNER_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_USER_ID = UUID("20000000-0000-4000-8000-000000000001")
FOOD_CATEGORY_ID = UUID("30000000-0000-4000-8000-000000000001")
PRIVATE_CATEGORY_ID = UUID("40000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


async def _seed_owners(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add_all(
            [
                User(
                    id=OWNER_ID,
                    email="owner@example.test",
                    name="Owner",
                    default_currency="INR",
                    timezone="Asia/Kolkata",
                ),
                User(
                    id=OTHER_USER_ID,
                    email="other@example.test",
                    name="Other",
                    default_currency="INR",
                    timezone="UTC",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Category(
                    id=FOOD_CATEGORY_ID,
                    name="Food",
                    normalized_name="food",
                ),
                Category(
                    id=PRIVATE_CATEGORY_ID,
                    user_id=OTHER_USER_ID,
                    name="Private",
                    normalized_name="private",
                ),
            ]
        )


@pytest.mark.database
@pytest.mark.asyncio
async def test_manual_create_round_trips_decimal_and_enforces_category_scope(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = LedgerService(isolated_database, clock=lambda: NOW)
    command = parse_create_transaction(
        amount="123456789.1234",
        currency="INR",
        transaction_type=TransactionType.EXPENSE,
        description="  Team lunch ",
        transaction_date=datetime(2026, 7, 24, 8, 30, tzinfo=UTC),
        category_id=FOOD_CATEGORY_ID,
    )

    created = await service.create_transaction(OWNER_ID, command)

    assert created.amount == Decimal("123456789.1234")
    assert created.description == "Team lunch"
    assert created.category_name == "Food"
    assert (await service.get_transaction(OWNER_ID, created.id)) == created

    with pytest.raises(LedgerNotFoundError) as hidden:
        await service.get_transaction(OTHER_USER_ID, created.id)
    assert hidden.value.code == "TRANSACTION_NOT_FOUND"

    cross_tenant_command = parse_create_transaction(
        amount="20.00",
        currency="INR",
        transaction_type=TransactionType.EXPENSE,
        description="Must not persist",
        transaction_date=NOW,
        category_id=PRIVATE_CATEGORY_ID,
    )
    with pytest.raises(LedgerNotFoundError) as rejected:
        await service.create_transaction(OWNER_ID, cross_tenant_command)
    assert rejected.value.code == "CATEGORY_NOT_FOUND"

    page = await service.list_transactions(OWNER_ID)
    assert [edge.node.id for edge in page.edges] == [created.id]


@pytest.mark.database
@pytest.mark.asyncio
async def test_summaries_follow_status_type_currency_and_local_month_semantics(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    rows = [
        _transaction("100.1000", TransactionType.EXPENSE, category_id=FOOD_CATEGORY_ID),
        _transaction("50.0000", TransactionType.SHARED_EXPENSE),
        _transaction("10.0500", TransactionType.REFUND, category_id=FOOD_CATEGORY_ID),
        _transaction("200.0000", TransactionType.INCOME),
        _transaction("999.0000", TransactionType.TRANSFER),
        _transaction(
            "400.0000",
            TransactionType.EXPENSE,
            status=TransactionStatus.PENDING,
        ),
        _transaction(
            "500.0000",
            TransactionType.EXPENSE,
            status=TransactionStatus.VOIDED,
        ),
        _transaction("700.0000", TransactionType.EXPENSE, currency="USD"),
        _transaction(
            "25.0000",
            TransactionType.EXPENSE,
            occurred_at=datetime(2026, 6, 30, 18, 29, 59, tzinfo=UTC),
        ),
        _transaction(
            "30.0000",
            TransactionType.EXPENSE,
            occurred_at=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
        ),
    ]
    async with isolated_database.session_factory()() as session, session.begin():
        session.add_all(rows)

    service = LedgerService(isolated_database, clock=lambda: NOW)
    summary = await service.financial_summary(OWNER_ID)
    category_totals = await service.spending_by_category(OWNER_ID)
    monthly = await service.monthly_spending(OWNER_ID, months=3)

    assert summary.currency == "INR"
    assert summary.spent == Decimal("140.0500")
    assert summary.income == Decimal("200.0000")
    assert summary.transaction_count == 5
    assert summary.period_start.isoformat() == "2026-07-01"
    assert summary.period_end.isoformat() == "2026-08-01"

    assert [
        (item.category_name, item.amount, item.share_percentage) for item in category_totals
    ] == [
        ("Food", Decimal("90.0500"), 64),
        ("Uncategorized", Decimal("50.0000"), 36),
    ]
    assert [(item.month_start.isoformat(), item.amount) for item in monthly] == [
        ("2026-05-01", Decimal("0.0000")),
        ("2026-06-01", Decimal("55.0000")),
        ("2026-07-01", Decimal("140.0500")),
    ]


@pytest.mark.database
@pytest.mark.asyncio
async def test_keyset_pages_have_no_duplicates_for_equal_timestamps(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    occurred_at = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    transaction_ids = [
        UUID("50000000-0000-4000-8000-000000000003"),
        UUID("50000000-0000-4000-8000-000000000002"),
        UUID("50000000-0000-4000-8000-000000000001"),
    ]
    async with isolated_database.session_factory()() as session, session.begin():
        session.add_all(
            [
                _transaction(
                    "1.0000",
                    TransactionType.EXPENSE,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                )
                for transaction_id in transaction_ids
            ]
        )

    service = LedgerService(isolated_database, clock=lambda: NOW)
    first_page = await service.list_transactions(OWNER_ID, first=2)
    second_page = await service.list_transactions(
        OWNER_ID,
        first=2,
        after=first_page.end_cursor,
    )

    assert [edge.node.id for edge in first_page.edges] == transaction_ids[:2]
    assert first_page.has_next_page is True
    assert [edge.node.id for edge in second_page.edges] == transaction_ids[2:]
    assert second_page.has_next_page is False
    assert not (
        {edge.node.id for edge in first_page.edges} & {edge.node.id for edge in second_page.edges}
    )


def _transaction(
    amount: str,
    transaction_type: TransactionType,
    *,
    transaction_id: UUID | None = None,
    category_id: UUID | None = None,
    currency: str = "INR",
    occurred_at: datetime = NOW,
    status: TransactionStatus = TransactionStatus.POSTED,
) -> LedgerTransaction:
    return LedgerTransaction(
        id=transaction_id or uuid4(),
        user_id=OWNER_ID,
        amount=Decimal(amount),
        currency=currency,
        transaction_type=transaction_type,
        description=f"{transaction_type.value} test",
        transaction_date=occurred_at,
        status=status,
        category_id=category_id,
    )
