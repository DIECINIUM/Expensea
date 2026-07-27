from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.categorization.service import CategorizationService
from app.db.session import Database
from app.domain.enums import TransactionStatus, TransactionType
from app.ledger.commands import parse_create_transaction
from app.ledger.errors import LedgerNotFoundError
from app.ledger.service import LedgerService
from app.models import Category, User

OWNER_ID = UUID("10000000-0000-4000-8000-000000000001")
FOOD_ID = UUID("70000000-0000-4000-8000-000000000001")
TRAVEL_ID = UUID("70000000-0000-4000-8000-000000000002")


async def _seed(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=OWNER_ID,
                email="category-owner@example.test",
                name="Category Owner",
                default_currency="INR",
                timezone="Asia/Kolkata",
            )
        )
        session.add_all(
            [
                Category(id=FOOD_ID, name="Food", normalized_name="food"),
                Category(id=TRAVEL_ID, name="Travel", normalized_name="travel"),
            ]
        )


def _command(description: str, merchant: str | None = None):
    return parse_create_transaction(
        amount="100.0000",
        currency="INR",
        transaction_type=TransactionType.EXPENSE,
        description=description,
        transaction_date=datetime.now(UTC),
        status=TransactionStatus.POSTED,
        merchant_name=merchant,
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_correction_is_audited_and_teaches_merchant_mapping(
    isolated_database: Database,
) -> None:
    await _seed(isolated_database)
    ledger = LedgerService(isolated_database)
    categorization = CategorizationService(isolated_database)
    first = await ledger.create_transaction(OWNER_ID, _command("Lunch order", "Example Cafe"))

    correction = await categorization.correct(OWNER_ID, first.id, FOOD_ID)
    second = await ledger.create_transaction(
        OWNER_ID, _command("Different description", "Example Cafe")
    )
    history = await categorization.list_corrections(OWNER_ID)

    assert correction.previous_category_name is None
    assert correction.corrected_category_name == "Food"
    assert second.category_name == "Food"
    assert second.category_source is not None
    assert second.category_source.value == "merchant_map"
    assert [item.id for item in history] == [correction.id]


@pytest.mark.database
@pytest.mark.asyncio
async def test_user_rule_has_precedence_and_owner_scope(
    isolated_database: Database,
) -> None:
    await _seed(isolated_database)
    categorization = CategorizationService(isolated_database)
    await categorization.create_rule(OWNER_ID, pattern="metro", category_id=TRAVEL_ID, priority=10)

    transaction = await LedgerService(isolated_database).create_transaction(
        OWNER_ID, _command("City Metro commute", "Example Cafe")
    )

    assert transaction.category_name == "Travel"
    assert transaction.category_source is not None
    assert transaction.category_source.value == "user_rule"

    with pytest.raises(LedgerNotFoundError):
        await categorization.correct(uuid4(), transaction.id, FOOD_ID)
