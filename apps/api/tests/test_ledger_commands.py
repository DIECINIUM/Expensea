"""Boundary validation for deterministic manual transactions."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.enums import TransactionStatus, TransactionType
from app.ledger.commands import (
    parse_create_category,
    parse_create_transaction,
    parse_currency,
)
from app.ledger.errors import LedgerValidationError


def test_create_transaction_normalizes_exact_values() -> None:
    command = parse_create_transaction(
        amount="1200.1250",
        currency=" inr ",
        transaction_type=TransactionType.EXPENSE,
        description="  Team   lunch  ",
        transaction_date=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        category_id=UUID("00000000-0000-4000-8000-000000000001"),
    )

    assert command.amount == Decimal("1200.1250")
    assert command.currency == "INR"
    assert command.description == "Team lunch"
    assert command.status is TransactionStatus.POSTED
    assert command.transaction_date == datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "amount",
    [
        "",
        " 1.00",
        "+1.00",
        "-1.00",
        "0",
        "NaN",
        "Infinity",
        "1.00001",
        "1000000000000000",
        "not-money",
    ],
)
def test_create_transaction_rejects_invalid_amounts(amount: str) -> None:
    with pytest.raises(LedgerValidationError) as exc_info:
        parse_create_transaction(
            amount=amount,
            currency="INR",
            transaction_type=TransactionType.EXPENSE,
            description="Lunch",
            transaction_date=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        )

    assert exc_info.value.code == "INVALID_AMOUNT"
    assert exc_info.value.field == "amount"


def test_create_transaction_requires_an_aware_date() -> None:
    with pytest.raises(LedgerValidationError) as exc_info:
        parse_create_transaction(
            amount="1.00",
            currency="INR",
            transaction_type=TransactionType.EXPENSE,
            description="Lunch",
            transaction_date=datetime(2026, 7, 24, 12, 0),
        )

    assert exc_info.value.code == "INVALID_TRANSACTION_DATE"


def test_create_transaction_rejects_blank_description() -> None:
    with pytest.raises(LedgerValidationError) as exc_info:
        parse_create_transaction(
            amount="1.00",
            currency="INR",
            transaction_type=TransactionType.EXPENSE,
            description=" \t ",
            transaction_date=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        )

    assert exc_info.value.code == "INVALID_DESCRIPTION"


def test_currency_support_is_explicit() -> None:
    assert parse_currency("usd") == "USD"
    with pytest.raises(LedgerValidationError) as exc_info:
        parse_currency("ZZZ")
    assert exc_info.value.code == "UNSUPPORTED_CURRENCY"


def test_category_and_merchant_names_are_normalized_at_the_boundary() -> None:
    category = parse_create_category(name="  Work   Travel ")
    transaction = parse_create_transaction(
        amount="10.00",
        currency="INR",
        transaction_type=TransactionType.EXPENSE,
        description="Train",
        transaction_date=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        merchant_name="  Rail   Desk ",
    )

    assert category.name == "Work Travel"
    assert category.normalized_name == "work travel"
    assert transaction.merchant_name == "Rail Desk"
    assert transaction.merchant_normalized_name == "rail desk"
