"""PostgreSQL integration tests for recurring-payment workflows."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.db.session import Database
from app.domain.enums import (
    RecurrenceRule,
    RecurringPaymentStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.ledger.errors import LedgerConflictError, LedgerNotFoundError, LedgerValidationError
from app.ledger.recurring_commands import (
    CreateRecurringPaymentCommand,
    parse_create_recurring_payment,
    parse_record_recurring_payment,
    parse_recurring_status_transition,
    parse_upcoming_recurring_window,
)
from app.ledger.recurring_service import RecurringPaymentService, advance_expected_date
from app.models import LedgerTransaction, Merchant, User

OWNER_ID = UUID("71000000-0000-4000-8000-000000000001")
OTHER_USER_ID = UUID("72000000-0000-4000-8000-000000000001")


async def _seed_users(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add_all(
            [
                User(
                    id=OWNER_ID,
                    email="recurring-owner@example.test",
                    name="Recurring Owner",
                    default_currency="INR",
                    timezone="Asia/Kolkata",
                ),
                User(
                    id=OTHER_USER_ID,
                    email="recurring-other@example.test",
                    name="Recurring Other",
                    default_currency="INR",
                    timezone="UTC",
                ),
            ]
        )


def _create_command(
    *,
    amount: str = "649.0000",
    currency: str = "INR",
    merchant_name: str = "Netflix",
    recurrence_rule: RecurrenceRule = RecurrenceRule.MONTHLY,
    next_expected_date: date = date(2024, 1, 31),
) -> CreateRecurringPaymentCommand:
    return parse_create_recurring_payment(
        amount=amount,
        currency=currency,
        merchant_name=merchant_name,
        recurrence_rule=recurrence_rule,
        next_expected_date=next_expected_date,
    )


@pytest.mark.parametrize(
    ("current", "rule", "expected"),
    [
        (date(2024, 1, 31), RecurrenceRule.MONTHLY, date(2024, 2, 29)),
        (date(2023, 1, 31), RecurrenceRule.MONTHLY, date(2023, 2, 28)),
        (date(2024, 2, 29), RecurrenceRule.YEARLY, date(2025, 2, 28)),
        (date(2024, 11, 30), RecurrenceRule.QUARTERLY, date(2025, 2, 28)),
        (date(2026, 7, 24), RecurrenceRule.WEEKLY, date(2026, 7, 31)),
    ],
)
def test_advance_expected_date_uses_calendar_rules(
    current: date,
    rule: RecurrenceRule,
    expected: date,
) -> None:
    assert advance_expected_date(current, rule) == expected


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"amount": "1.00001"}, "INVALID_AMOUNT"),
        ({"currency": "BTC"}, "UNSUPPORTED_CURRENCY"),
        ({"merchant_name": " \t "}, "INVALID_MERCHANT"),
    ],
)
def test_create_command_rejects_invalid_money_currency_and_merchant(
    overrides: dict[str, str],
    expected_code: str,
) -> None:
    values = {
        "amount": "649.0000",
        "currency": "INR",
        "merchant_name": "Netflix",
    }
    values.update(overrides)

    with pytest.raises(LedgerValidationError) as invalid:
        parse_create_recurring_payment(
            **values,
            recurrence_rule=RecurrenceRule.MONTHLY,
            next_expected_date=date(2026, 8, 1),
        )
    assert invalid.value.code == expected_code


def test_record_command_requires_aware_transaction_datetime() -> None:
    with pytest.raises(LedgerValidationError) as invalid:
        parse_record_recurring_payment(
            recurring_payment_id=OWNER_ID,
            expected_date=date(2026, 8, 1),
            transaction_date=datetime(2026, 8, 1, 10, 0),
        )
    assert invalid.value.code == "INVALID_TRANSACTION_DATE"


def test_upcoming_window_rejects_reverse_dates() -> None:
    with pytest.raises(LedgerValidationError) as invalid:
        parse_upcoming_recurring_window(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 8, 1),
        )
    assert invalid.value.code == "INVALID_DATE_WINDOW"


@pytest.mark.database
@pytest.mark.asyncio
async def test_create_reuses_canonical_merchant_and_scopes_reads(
    isolated_database: Database,
) -> None:
    await _seed_users(isolated_database)
    service = RecurringPaymentService(isolated_database)

    first = await service.create(OWNER_ID, _create_command())
    second = await service.create(
        OWNER_ID,
        _create_command(
            amount="799.0000",
            merchant_name="  NETFLIX  ",
            next_expected_date=date(2024, 2, 29),
        ),
    )

    assert first.merchant_id == second.merchant_id
    assert first.merchant_name == "Netflix"
    assert [item.id for item in await service.list(OWNER_ID)] == [first.id, second.id]
    assert await service.get(OWNER_ID, first.id) == first
    assert await service.list(OTHER_USER_ID) == ()

    with pytest.raises(LedgerNotFoundError) as hidden:
        await service.get(OTHER_USER_ID, first.id)
    assert hidden.value.code == "RECURRING_PAYMENT_NOT_FOUND"

    async with isolated_database.session_factory()() as session:
        merchant_count = await session.scalar(select(func.count(Merchant.id)))
    assert merchant_count == 1


@pytest.mark.database
@pytest.mark.asyncio
async def test_status_transitions_are_explicit_and_ended_is_terminal(
    isolated_database: Database,
) -> None:
    await _seed_users(isolated_database)
    service = RecurringPaymentService(isolated_database)
    payment = await service.create(OWNER_ID, _create_command())

    paused = await service.transition_status(
        OWNER_ID,
        parse_recurring_status_transition(
            recurring_payment_id=payment.id,
            target_status=RecurringPaymentStatus.PAUSED,
        ),
    )
    assert paused.status is RecurringPaymentStatus.PAUSED

    active = await service.transition_status(
        OWNER_ID,
        parse_recurring_status_transition(
            recurring_payment_id=payment.id,
            target_status=RecurringPaymentStatus.ACTIVE,
        ),
    )
    assert active.status is RecurringPaymentStatus.ACTIVE

    ended = await service.transition_status(
        OWNER_ID,
        parse_recurring_status_transition(
            recurring_payment_id=payment.id,
            target_status=RecurringPaymentStatus.ENDED,
        ),
    )
    assert ended.status is RecurringPaymentStatus.ENDED

    with pytest.raises(LedgerConflictError) as terminal:
        await service.transition_status(
            OWNER_ID,
            parse_recurring_status_transition(
                recurring_payment_id=payment.id,
                target_status=RecurringPaymentStatus.ACTIVE,
            ),
        )
    assert terminal.value.code == "INVALID_RECURRING_STATUS_TRANSITION"


@pytest.mark.database
@pytest.mark.asyncio
async def test_record_due_payment_creates_one_expense_and_rejects_duplicate(
    isolated_database: Database,
) -> None:
    await _seed_users(isolated_database)
    service = RecurringPaymentService(isolated_database)
    payment = await service.create(OWNER_ID, _create_command())
    occurred_at = datetime(2024, 1, 31, 18, 30, tzinfo=UTC)
    command = parse_record_recurring_payment(
        recurring_payment_id=payment.id,
        expected_date=date(2024, 1, 31),
        transaction_date=occurred_at,
    )

    recorded = await service.record_due_payment(OWNER_ID, command)

    assert recorded.recorded_expected_date == date(2024, 1, 31)
    assert recorded.payment.next_expected_date == date(2024, 2, 29)
    assert recorded.payment.amount == Decimal("649.0000")

    async with isolated_database.session_factory()() as session:
        transaction = await session.scalar(
            select(LedgerTransaction).where(
                LedgerTransaction.id == recorded.transaction_id,
            )
        )
    assert transaction is not None
    assert transaction.user_id == OWNER_ID
    assert transaction.amount == Decimal("649.0000")
    assert transaction.transaction_type is TransactionType.EXPENSE
    assert transaction.source is TransactionSource.MANUAL
    assert transaction.status is TransactionStatus.POSTED
    assert transaction.merchant_id == payment.merchant_id

    with pytest.raises(LedgerConflictError) as duplicate:
        await service.record_due_payment(OWNER_ID, command)
    assert duplicate.value.code == "RECURRING_OCCURRENCE_CONFLICT"

    async with isolated_database.session_factory()() as session:
        transaction_count = await session.scalar(select(func.count(LedgerTransaction.id)))
    assert transaction_count == 1


@pytest.mark.database
@pytest.mark.asyncio
async def test_concurrent_recording_serializes_one_expected_occurrence(
    isolated_database: Database,
) -> None:
    await _seed_users(isolated_database)
    service = RecurringPaymentService(isolated_database)
    payment = await service.create(OWNER_ID, _create_command())
    command = parse_record_recurring_payment(
        recurring_payment_id=payment.id,
        expected_date=date(2024, 1, 31),
        transaction_date=datetime(2024, 1, 31, 18, 30, tzinfo=UTC),
    )

    results = await asyncio.gather(
        service.record_due_payment(OWNER_ID, command),
        service.record_due_payment(OWNER_ID, command),
        return_exceptions=True,
    )

    conflicts = [item for item in results if isinstance(item, LedgerConflictError)]
    successes = [item for item in results if not isinstance(item, BaseException)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code == "RECURRING_OCCURRENCE_CONFLICT"

    async with isolated_database.session_factory()() as session:
        transaction_count = await session.scalar(select(func.count(LedgerTransaction.id)))
    assert transaction_count == 1


@pytest.mark.database
@pytest.mark.asyncio
async def test_paused_stale_and_cross_tenant_occurrences_cannot_write(
    isolated_database: Database,
) -> None:
    await _seed_users(isolated_database)
    service = RecurringPaymentService(isolated_database)
    payment = await service.create(OWNER_ID, _create_command())
    record = parse_record_recurring_payment(
        recurring_payment_id=payment.id,
        expected_date=date(2023, 12, 31),
        transaction_date=datetime(2024, 1, 31, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(LedgerConflictError) as stale:
        await service.record_due_payment(OWNER_ID, record)
    assert stale.value.code == "RECURRING_OCCURRENCE_CONFLICT"

    await service.transition_status(
        OWNER_ID,
        parse_recurring_status_transition(
            recurring_payment_id=payment.id,
            target_status=RecurringPaymentStatus.PAUSED,
        ),
    )
    current_record = parse_record_recurring_payment(
        recurring_payment_id=payment.id,
        expected_date=date(2024, 1, 31),
        transaction_date=datetime(2024, 1, 31, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(LedgerConflictError) as paused:
        await service.record_due_payment(OWNER_ID, current_record)
    assert paused.value.code == "RECURRING_PAYMENT_NOT_ACTIVE"

    with pytest.raises(LedgerNotFoundError) as cross_tenant:
        await service.record_due_payment(OTHER_USER_ID, current_record)
    assert cross_tenant.value.code == "RECURRING_PAYMENT_NOT_FOUND"

    with pytest.raises(LedgerNotFoundError) as cross_tenant_transition:
        await service.transition_status(
            OTHER_USER_ID,
            parse_recurring_status_transition(
                recurring_payment_id=payment.id,
                target_status=RecurringPaymentStatus.ENDED,
            ),
        )
    assert cross_tenant_transition.value.code == "RECURRING_PAYMENT_NOT_FOUND"

    async with isolated_database.session_factory()() as session:
        transaction_count = await session.scalar(select(func.count(LedgerTransaction.id)))
    assert transaction_count == 0


@pytest.mark.database
@pytest.mark.asyncio
async def test_upcoming_totals_group_exact_active_amounts_by_currency(
    isolated_database: Database,
) -> None:
    await _seed_users(isolated_database)
    service = RecurringPaymentService(isolated_database)
    inr_one = await service.create(
        OWNER_ID,
        _create_command(amount="649.1234", next_expected_date=date(2026, 8, 1)),
    )
    await service.create(
        OWNER_ID,
        _create_command(
            amount="350.8766",
            merchant_name="Mobile plan",
            next_expected_date=date(2026, 8, 31),
        ),
    )
    paused = await service.create(
        OWNER_ID,
        _create_command(
            amount="500.0000",
            merchant_name="Paused plan",
            next_expected_date=date(2026, 8, 10),
        ),
    )
    await service.transition_status(
        OWNER_ID,
        parse_recurring_status_transition(
            recurring_payment_id=paused.id,
            target_status=RecurringPaymentStatus.PAUSED,
        ),
    )
    await service.create(
        OWNER_ID,
        _create_command(
            amount="10.2500",
            currency="USD",
            merchant_name="Cloud service",
            next_expected_date=date(2026, 8, 15),
        ),
    )
    await service.create(
        OWNER_ID,
        _create_command(
            amount="999.0000",
            merchant_name="Outside window",
            next_expected_date=date(2026, 9, 1),
        ),
    )
    await service.create(
        OTHER_USER_ID,
        _create_command(
            amount="8000.0000",
            merchant_name="Other owner",
            next_expected_date=date(2026, 8, 15),
        ),
    )

    totals = await service.upcoming_totals(
        OWNER_ID,
        parse_upcoming_recurring_window(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
        ),
    )

    assert [(item.currency, item.amount, item.payment_count) for item in totals] == [
        ("INR", Decimal("1000.0000"), 2),
        ("USD", Decimal("10.2500"), 1),
    ]
    assert all(item.window_start == date(2026, 8, 1) for item in totals)
    assert all(item.window_end == date(2026, 8, 31) for item in totals)
    assert await service.get(OWNER_ID, inr_one.id) == inr_one
