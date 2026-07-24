"""Development seed safety and PostgreSQL behavior."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.config import AppEnvironment, Settings
from app.db.session import Database
from app.ledger.commands import parse_currency
from app.ledger.obligation_service import ObligationService
from app.ledger.recurring_commands import parse_upcoming_recurring_window
from app.ledger.recurring_service import RecurringPaymentService
from app.ledger.service import LedgerService
from app.models import (
    Category,
    LedgerTransaction,
    ObligationSettlement,
    Payable,
    Person,
    Receivable,
    RecurringPayment,
)
from app.seed import DEMO_USER_ID, ensure_demo_seed_allowed, seed_demo_data

pytestmark = pytest.mark.database

_FOOD_CATEGORY_ID = UUID("00000000-0000-4000-8000-000000000001")
_SYSTEM_CATEGORIES = (
    (_FOOD_CATEGORY_ID, "Food", "food", None),
    (
        UUID("00000000-0000-4000-8000-000000000002"),
        "Food Delivery",
        "food delivery",
        _FOOD_CATEGORY_ID,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000004"),
        "Grocery",
        "grocery",
        _FOOD_CATEGORY_ID,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000005"),
        "Travel",
        "travel",
        None,
    ),
    (
        UUID("00000000-0000-4000-8000-000000000006"),
        "Shopping",
        "shopping",
        None,
    ),
)


def test_demo_seed_is_restricted_to_development(test_settings: Settings) -> None:
    with pytest.raises(RuntimeError, match="APP_ENV=development"):
        ensure_demo_seed_allowed(test_settings)

    development_settings = test_settings.model_copy(update={"app_env": AppEnvironment.DEVELOPMENT})
    ensure_demo_seed_allowed(development_settings)


async def _insert_system_categories(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add_all(
            [
                Category(
                    id=category_id,
                    user_id=None,
                    name=name,
                    normalized_name=normalized_name,
                    parent_category_id=parent_id,
                )
                for category_id, name, normalized_name, parent_id in _SYSTEM_CATEGORIES
            ]
        )


async def _owned_count(
    database: Database,
    model: type[LedgerTransaction]
    | type[Person]
    | type[Receivable]
    | type[Payable]
    | type[ObligationSettlement]
    | type[RecurringPayment],
) -> int:
    async with database.session_factory()() as session:
        count = await session.scalar(
            select(func.count()).select_from(model).where(model.user_id == DEMO_USER_ID)
        )
    return int(count or 0)


async def test_demo_seed_is_idempotent_and_financially_consistent(
    isolated_database: Database,
) -> None:
    await _insert_system_categories(isolated_database)
    today = date(2026, 7, 24)

    first = await seed_demo_data(isolated_database, today=today)
    second = await seed_demo_data(isolated_database, today=today)

    assert first.created is True
    assert first.transaction_count == 5
    assert first.obligation_count == 2
    assert second.created is False
    assert await _owned_count(isolated_database, LedgerTransaction) == 5
    assert await _owned_count(isolated_database, Person) == 1
    assert await _owned_count(isolated_database, Receivable) == 1
    assert await _owned_count(isolated_database, Payable) == 1
    assert await _owned_count(isolated_database, ObligationSettlement) == 1
    assert await _owned_count(isolated_database, RecurringPayment) == 1

    def clock() -> datetime:
        return datetime(2026, 7, 24, 12, tzinfo=UTC)

    financial_summary = await LedgerService(
        isolated_database,
        clock=clock,
    ).financial_summary(DEMO_USER_ID)
    assert financial_summary.currency == parse_currency("INR")
    assert financial_summary.spent == Decimal("3020.5000")
    assert financial_summary.income == Decimal("75000.0000")
    assert financial_summary.transaction_count == 5

    obligation_totals = await ObligationService(
        isolated_database,
        clock=clock,
    ).outstanding_totals(DEMO_USER_ID)
    assert len(obligation_totals) == 1
    assert obligation_totals[0].receivable == Decimal("1200.0000")
    assert obligation_totals[0].payable == Decimal("600.0000")
    assert obligation_totals[0].net_exposure == Decimal("600.0000")

    recurring_totals = await RecurringPaymentService(isolated_database).upcoming_totals(
        DEMO_USER_ID,
        parse_upcoming_recurring_window(
            start_date=today,
            end_date=date(2026, 8, 24),
        ),
    )
    assert len(recurring_totals) == 1
    assert recurring_totals[0].amount == Decimal("649.0000")
    assert recurring_totals[0].payment_count == 1
