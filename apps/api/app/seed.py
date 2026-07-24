"""Idempotent development-only data for a usable fresh-clone ledger."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    DEFAULT_DEV_USER_ID,
    AppEnvironment,
    Settings,
    get_settings,
)
from app.db.session import Database
from app.domain.enums import (
    ObligationStatus,
    RecurrenceRule,
    RecurringPaymentStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models import (
    Category,
    LedgerTransaction,
    Merchant,
    ObligationSettlement,
    Payable,
    Person,
    Receivable,
    RecurringPayment,
    User,
)

DEMO_USER_ID = DEFAULT_DEV_USER_ID
DEMO_PERSON_ID = UUID("20000000-0000-4000-8000-000000000001")
DEMO_RECEIVABLE_ID = UUID("40000000-0000-4000-8000-000000000001")
DEMO_PAYABLE_ID = UUID("50000000-0000-4000-8000-000000000001")
DEMO_SETTLEMENT_ID = UUID("60000000-0000-4000-8000-000000000001")
DEMO_RECURRING_PAYMENT_ID = UUID("70000000-0000-4000-8000-000000000001")

_FOOD_DELIVERY_CATEGORY_ID = UUID("00000000-0000-4000-8000-000000000002")
_GROCERY_CATEGORY_ID = UUID("00000000-0000-4000-8000-000000000004")
_TRAVEL_CATEGORY_ID = UUID("00000000-0000-4000-8000-000000000005")
_SHOPPING_CATEGORY_ID = UUID("00000000-0000-4000-8000-000000000006")
_REQUIRED_CATEGORY_IDS = frozenset(
    {
        _FOOD_DELIVERY_CATEGORY_ID,
        _GROCERY_CATEGORY_ID,
        _TRAVEL_CATEGORY_ID,
        _SHOPPING_CATEGORY_ID,
    }
)

_FRESH_BASKET_MERCHANT_ID = UUID("10000000-0000-4000-8000-000000000001")
_SWIGGY_MERCHANT_ID = UUID("10000000-0000-4000-8000-000000000002")
_LOCAL_STORE_MERCHANT_ID = UUID("10000000-0000-4000-8000-000000000003")
_NETFLIX_MERCHANT_ID = UUID("10000000-0000-4000-8000-000000000004")

_GROCERY_TRANSACTION_ID = UUID("30000000-0000-4000-8000-000000000001")
_DELIVERY_TRANSACTION_ID = UUID("30000000-0000-4000-8000-000000000002")
_SALARY_TRANSACTION_ID = UUID("30000000-0000-4000-8000-000000000003")
_REFUND_TRANSACTION_ID = UUID("30000000-0000-4000-8000-000000000004")
_SHARED_CAB_TRANSACTION_ID = UUID("30000000-0000-4000-8000-000000000005")


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    """Summary suitable for CLI output and integration assertions."""

    created: bool
    user_id: UUID
    transaction_count: int
    person_count: int
    obligation_count: int
    recurring_payment_count: int


def ensure_demo_seed_allowed(settings: Settings) -> None:
    """Keep sample financial data out of every deployed environment."""
    if settings.app_env is not AppEnvironment.DEVELOPMENT:
        msg = "Demo data can only be seeded when APP_ENV=development."
        raise RuntimeError(msg)
    if not settings.dev_auth_enabled:
        msg = "Demo data requires DEV_AUTH_ENABLED=true."
        raise RuntimeError(msg)


async def seed_demo_data(
    database: Database,
    *,
    user_id: UUID = DEMO_USER_ID,
    today: date | None = None,
) -> DemoSeedResult:
    """Create one complete demo ledger, or leave an existing profile untouched."""
    seed_date = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()

    async with database.session_factory()() as session, session.begin():
        existing_user = await session.get(User, user_id)
        if existing_user is not None:
            return DemoSeedResult(
                created=False,
                user_id=user_id,
                transaction_count=0,
                person_count=0,
                obligation_count=0,
                recurring_payment_count=0,
            )

        available_category_ids = set(
            (
                await session.scalars(
                    select(Category.id).where(Category.id.in_(_REQUIRED_CATEGORY_IDS))
                )
            ).all()
        )
        missing_category_ids = _REQUIRED_CATEGORY_IDS - available_category_ids
        if missing_category_ids:
            msg = "Phase 1 system categories are missing; run Alembic migrations first."
            raise RuntimeError(msg)

        await _insert_demo_rows(session, user_id=user_id, today=seed_date)

    return DemoSeedResult(
        created=True,
        user_id=user_id,
        transaction_count=5,
        person_count=1,
        obligation_count=2,
        recurring_payment_count=1,
    )


async def _insert_demo_rows(
    session: AsyncSession,
    *,
    user_id: UUID,
    today: date,
) -> None:
    month_start = today.replace(day=1)
    grocery_date = _current_month_date(today, days_ago=12)
    delivery_date = _current_month_date(today, days_ago=8)
    salary_date = month_start
    refund_date = _current_month_date(today, days_ago=3)
    shared_cab_date = _current_month_date(today, days_ago=1)
    obligation_issued_date = _current_month_date(today, days_ago=14)

    session.add(
        User(
            id=user_id,
            email="demo@spendgraph.local",
            name="SpendGraph Demo",
            default_currency="INR",
            timezone="Asia/Kolkata",
        )
    )
    await session.flush()

    session.add_all(
        [
            Merchant(
                id=_FRESH_BASKET_MERCHANT_ID,
                normalized_name="fresh basket",
                display_name="Fresh Basket",
                merchant_category="grocery",
            ),
            Merchant(
                id=_SWIGGY_MERCHANT_ID,
                normalized_name="swiggy",
                display_name="Swiggy",
                domain="swiggy.com",
                merchant_category="food delivery",
            ),
            Merchant(
                id=_LOCAL_STORE_MERCHANT_ID,
                normalized_name="local store",
                display_name="Local Store",
                merchant_category="shopping",
            ),
            Merchant(
                id=_NETFLIX_MERCHANT_ID,
                normalized_name="netflix",
                display_name="Netflix",
                domain="netflix.com",
                merchant_category="entertainment",
            ),
        ]
    )
    await session.flush()

    session.add_all(
        [
            LedgerTransaction(
                id=_GROCERY_TRANSACTION_ID,
                user_id=user_id,
                amount=Decimal("1850.5000"),
                currency="INR",
                transaction_type=TransactionType.EXPENSE,
                merchant_id=_FRESH_BASKET_MERCHANT_ID,
                category_id=_GROCERY_CATEGORY_ID,
                description="Weekly groceries",
                transaction_date=_local_instant(grocery_date, hour=18),
                source=TransactionSource.MANUAL,
                status=TransactionStatus.POSTED,
            ),
            LedgerTransaction(
                id=_DELIVERY_TRANSACTION_ID,
                user_id=user_id,
                amount=Decimal("420.0000"),
                currency="INR",
                transaction_type=TransactionType.EXPENSE,
                merchant_id=_SWIGGY_MERCHANT_ID,
                category_id=_FOOD_DELIVERY_CATEGORY_ID,
                description="Dinner delivery",
                transaction_date=_local_instant(delivery_date, hour=20),
                source=TransactionSource.MANUAL,
                status=TransactionStatus.POSTED,
            ),
            LedgerTransaction(
                id=_SALARY_TRANSACTION_ID,
                user_id=user_id,
                amount=Decimal("75000.0000"),
                currency="INR",
                transaction_type=TransactionType.INCOME,
                merchant_id=None,
                category_id=None,
                description="Monthly salary",
                transaction_date=_local_instant(salary_date, hour=10),
                source=TransactionSource.MANUAL,
                status=TransactionStatus.POSTED,
            ),
            LedgerTransaction(
                id=_REFUND_TRANSACTION_ID,
                user_id=user_id,
                amount=Decimal("150.0000"),
                currency="INR",
                transaction_type=TransactionType.REFUND,
                merchant_id=_LOCAL_STORE_MERCHANT_ID,
                category_id=_SHOPPING_CATEGORY_ID,
                description="Returned item refund",
                transaction_date=_local_instant(refund_date, hour=14),
                source=TransactionSource.MANUAL,
                status=TransactionStatus.POSTED,
            ),
            LedgerTransaction(
                id=_SHARED_CAB_TRANSACTION_ID,
                user_id=user_id,
                amount=Decimal("900.0000"),
                currency="INR",
                transaction_type=TransactionType.SHARED_EXPENSE,
                merchant_id=None,
                category_id=_TRAVEL_CATEGORY_ID,
                description="Shared airport cab",
                transaction_date=_local_instant(shared_cab_date, hour=9),
                source=TransactionSource.MANUAL,
                status=TransactionStatus.POSTED,
            ),
        ]
    )
    await session.flush()

    session.add(
        Person(
            id=DEMO_PERSON_ID,
            user_id=user_id,
            name="Priya",
            normalized_name="priya",
        )
    )
    await session.flush()

    session.add_all(
        [
            Receivable(
                id=DEMO_RECEIVABLE_ID,
                user_id=user_id,
                person_id=DEMO_PERSON_ID,
                amount=Decimal("2000.0000"),
                currency="INR",
                description="Shared trip",
                issued_date=obligation_issued_date,
                due_date=today + timedelta(days=10),
                status=ObligationStatus.PARTIALLY_PAID,
                transaction_id=None,
                confidence=None,
            ),
            Payable(
                id=DEMO_PAYABLE_ID,
                user_id=user_id,
                person_id=DEMO_PERSON_ID,
                amount=Decimal("600.0000"),
                currency="INR",
                description="Concert tickets",
                issued_date=obligation_issued_date,
                due_date=None,
                status=ObligationStatus.OPEN,
                transaction_id=None,
                confidence=None,
            ),
        ]
    )
    await session.flush()

    session.add(
        ObligationSettlement(
            id=DEMO_SETTLEMENT_ID,
            user_id=user_id,
            receivable_id=DEMO_RECEIVABLE_ID,
            payable_id=None,
            amount=Decimal("800.0000"),
            currency="INR",
            settled_at=_local_instant(_current_month_date(today, days_ago=2), hour=11),
            transaction_id=None,
            note="Demo partial settlement",
        )
    )
    session.add(
        RecurringPayment(
            id=DEMO_RECURRING_PAYMENT_ID,
            user_id=user_id,
            merchant_id=_NETFLIX_MERCHANT_ID,
            amount=Decimal("649.0000"),
            currency="INR",
            recurrence_rule=RecurrenceRule.MONTHLY,
            next_expected_date=today + timedelta(days=5),
            confidence=None,
            status=RecurringPaymentStatus.ACTIVE,
        )
    )


def _current_month_date(today: date, *, days_ago: int) -> date:
    return max(today - timedelta(days=days_ago), today.replace(day=1))


def _local_instant(day: date, *, hour: int) -> datetime:
    local = datetime.combine(
        day,
        time(hour=hour),
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )
    return local.astimezone(UTC)


async def _run_seed(settings: Settings) -> DemoSeedResult:
    ensure_demo_seed_allowed(settings)
    database = Database(settings.database_url)
    try:
        return await seed_demo_data(database, user_id=settings.dev_user_id)
    finally:
        await database.dispose()


def main() -> None:
    """Run the development seed from ``python -m app.seed``."""
    try:
        result = asyncio.run(_run_seed(get_settings()))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    if result.created:
        print(
            "Created demo ledger "
            f"{result.user_id}: {result.transaction_count} transactions, "
            f"{result.obligation_count} obligations, "
            f"{result.recurring_payment_count} recurring payment."
        )
    else:
        print(f"Demo ledger {result.user_id} already exists; no rows changed.")


if __name__ == "__main__":
    main()
