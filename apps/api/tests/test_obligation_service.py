"""PostgreSQL integration tests for owner-scoped obligation workflows."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.db.session import Database
from app.domain.enums import ObligationStatus, TransactionStatus, TransactionType
from app.ledger.errors import (
    LedgerConflictError,
    LedgerNotFoundError,
    LedgerValidationError,
)
from app.ledger.obligation_commands import (
    SettleObligationCommand,
    parse_create_obligation,
    parse_create_person,
    parse_settlement,
)
from app.ledger.obligation_dto import ObligationKind, SettlementResult
from app.ledger.obligation_service import ObligationService
from app.models import LedgerTransaction, ObligationSettlement, Receivable, User

OWNER_ID = UUID("11000000-0000-4000-8000-000000000001")
OTHER_USER_ID = UUID("22000000-0000-4000-8000-000000000001")
OWNER_TRANSACTION_ID = UUID("33000000-0000-4000-8000-000000000001")
OTHER_TRANSACTION_ID = UUID("44000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


async def _seed_owners(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add_all(
            [
                User(
                    id=OWNER_ID,
                    email="obligation-owner@example.test",
                    name="Obligation Owner",
                    default_currency="INR",
                    timezone="Asia/Kolkata",
                ),
                User(
                    id=OTHER_USER_ID,
                    email="obligation-other@example.test",
                    name="Other Owner",
                    default_currency="INR",
                    timezone="UTC",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                _transaction(OWNER_ID, OWNER_TRANSACTION_ID),
                _transaction(OTHER_USER_ID, OTHER_TRANSACTION_ID),
            ]
        )


def _service(database: Database) -> ObligationService:
    return ObligationService(database, clock=lambda: NOW)


def _transaction(user_id: UUID, transaction_id: UUID) -> LedgerTransaction:
    return LedgerTransaction(
        id=transaction_id,
        user_id=user_id,
        amount=Decimal("10.0000"),
        currency="INR",
        transaction_type=TransactionType.TRANSFER,
        description="Settlement reference",
        transaction_date=NOW,
        status=TransactionStatus.POSTED,
    )


def test_obligation_commands_reject_invalid_dates_and_text() -> None:
    person_id = UUID("55000000-0000-4000-8000-000000000001")

    with pytest.raises(LedgerValidationError) as blank_description:
        parse_create_obligation(
            person_id=person_id,
            amount="1.0000",
            currency="INR",
            description=" \t ",
            issued_date=date(2026, 7, 20),
        )
    assert blank_description.value.code == "INVALID_DESCRIPTION"

    with pytest.raises(LedgerValidationError) as invalid_due_date:
        parse_create_obligation(
            person_id=person_id,
            amount="1.0000",
            currency="INR",
            description="Loan",
            issued_date=date(2026, 7, 20),
            due_date=date(2026, 7, 19),
        )
    assert invalid_due_date.value.code == "INVALID_DUE_DATE"

    with pytest.raises(LedgerValidationError) as naive_settlement:
        parse_settlement(
            amount="1.0000",
            currency="INR",
            settled_at=datetime(2026, 7, 24, 12, 0),
        )
    assert naive_settlement.value.code == "INVALID_SETTLEMENT_DATE"


@pytest.mark.database
@pytest.mark.asyncio
async def test_people_are_normalized_unique_and_owner_scoped(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = _service(isolated_database)

    owner_person = await service.create_person(
        OWNER_ID,
        parse_create_person(name="  Rahul   Sharma "),
    )
    other_person = await service.create_person(
        OTHER_USER_ID,
        parse_create_person(name="Rahul Sharma"),
    )

    assert owner_person.name == "Rahul Sharma"
    assert await service.list_people(OWNER_ID) == (owner_person,)
    assert await service.list_people(OTHER_USER_ID) == (other_person,)

    with pytest.raises(LedgerConflictError) as duplicate:
        await service.create_person(
            OWNER_ID,
            parse_create_person(name="rahul sharma"),
        )
    assert duplicate.value.code == "PERSON_ALREADY_EXISTS"


@pytest.mark.database
@pytest.mark.asyncio
async def test_create_list_get_and_derived_overdue_preserve_stored_state(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = _service(isolated_database)
    person = await service.create_person(
        OWNER_ID,
        parse_create_person(name="Arjun"),
    )

    receivable = await service.create_receivable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="2000.1250",
            currency="inr",
            description="  Informal loan ",
            issued_date=date(2026, 7, 1),
            due_date=date(2026, 7, 20),
            transaction_id=OWNER_TRANSACTION_ID,
        ),
    )
    payable = await service.create_payable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="620.0000",
            currency="INR",
            description="Shared dinner",
            issued_date=date(2026, 7, 20),
            due_date=date(2026, 8, 1),
        ),
    )

    assert receivable.kind is ObligationKind.RECEIVABLE
    assert receivable.amount == Decimal("2000.1250")
    assert receivable.outstanding_amount == Decimal("2000.1250")
    assert receivable.settlement_status is ObligationStatus.OPEN
    assert receivable.effective_status is ObligationStatus.OVERDUE
    assert receivable.description == "Informal loan"
    assert payable.kind is ObligationKind.PAYABLE
    assert payable.effective_status is ObligationStatus.OPEN
    assert await service.list_receivables(OWNER_ID) == (receivable,)
    assert await service.list_payables(OWNER_ID) == (payable,)
    assert await service.get_receivable(OWNER_ID, receivable.id) == receivable
    assert await service.get_payable(OWNER_ID, payable.id) == payable

    async with isolated_database.session_factory()() as session:
        stored_status = await session.scalar(
            select(Receivable.status).where(Receivable.id == receivable.id)
        )
    assert stored_status is ObligationStatus.OPEN


@pytest.mark.database
@pytest.mark.asyncio
async def test_partial_and_full_receivable_settlement_is_exact_and_immutable(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = _service(isolated_database)
    person = await service.create_person(
        OWNER_ID,
        parse_create_person(name="Priya"),
    )
    receivable = await service.create_receivable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="100.0000",
            currency="INR",
            description="Cab split",
            issued_date=date(2026, 7, 20),
        ),
    )

    partial = await service.settle_receivable(
        OWNER_ID,
        receivable.id,
        parse_settlement(
            amount="40.2500",
            currency="INR",
            settled_at=NOW,
            transaction_id=OWNER_TRANSACTION_ID,
            note="First transfer",
        ),
    )
    assert partial.obligation.settlement_status is ObligationStatus.PARTIALLY_PAID
    assert partial.obligation.settled_amount == Decimal("40.2500")
    assert partial.obligation.outstanding_amount == Decimal("59.7500")
    assert await service.get_settlement(OWNER_ID, partial.settlement.id) == partial.settlement

    complete = await service.settle_receivable(
        OWNER_ID,
        receivable.id,
        parse_settlement(
            amount="59.7500",
            currency="INR",
            settled_at=NOW,
        ),
    )
    assert complete.obligation.settlement_status is ObligationStatus.PAID
    assert complete.obligation.settled_amount == Decimal("100.0000")
    assert complete.obligation.outstanding_amount == Decimal("0.0000")

    with pytest.raises(LedgerConflictError) as already_paid:
        await service.settle_receivable(
            OWNER_ID,
            receivable.id,
            parse_settlement(amount="1.0000", currency="INR", settled_at=NOW),
        )
    assert already_paid.value.code == "OBLIGATION_PAID"

    async with isolated_database.session_factory()() as session:
        settlement_count = await session.scalar(
            select(func.count(ObligationSettlement.id)).where(
                ObligationSettlement.receivable_id == receivable.id
            )
        )
    assert settlement_count == 2


@pytest.mark.database
@pytest.mark.asyncio
async def test_overpayment_currency_and_zero_fail_without_partial_writes(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = _service(isolated_database)
    person = await service.create_person(
        OWNER_ID,
        parse_create_person(name="Amit"),
    )
    receivable = await service.create_receivable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="100.0000",
            currency="INR",
            description="Hotel share",
            issued_date=date(2026, 7, 20),
        ),
    )
    await service.settle_receivable(
        OWNER_ID,
        receivable.id,
        parse_settlement(amount="40.0000", currency="INR", settled_at=NOW),
    )

    with pytest.raises(LedgerConflictError) as overpayment:
        await service.settle_receivable(
            OWNER_ID,
            receivable.id,
            parse_settlement(amount="70.0000", currency="INR", settled_at=NOW),
        )
    assert overpayment.value.code == "SETTLEMENT_EXCEEDS_OUTSTANDING"

    with pytest.raises(LedgerValidationError) as wrong_currency:
        await service.settle_receivable(
            OWNER_ID,
            receivable.id,
            parse_settlement(amount="10.0000", currency="USD", settled_at=NOW),
        )
    assert wrong_currency.value.code == "SETTLEMENT_CURRENCY_MISMATCH"

    with pytest.raises(LedgerValidationError) as zero:
        await service.settle_receivable(
            OWNER_ID,
            receivable.id,
            SettleObligationCommand(
                amount=Decimal("0.0000"),
                currency="INR",
                settled_at=NOW,
                transaction_id=None,
                note=None,
            ),
        )
    assert zero.value.code == "INVALID_AMOUNT"

    unchanged = await service.get_receivable(OWNER_ID, receivable.id)
    assert unchanged.settlement_status is ObligationStatus.PARTIALLY_PAID
    assert unchanged.settled_amount == Decimal("40.0000")
    assert unchanged.outstanding_amount == Decimal("60.0000")


@pytest.mark.database
@pytest.mark.asyncio
async def test_cross_tenant_references_are_indistinguishable_from_missing(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = _service(isolated_database)
    owner_person = await service.create_person(
        OWNER_ID,
        parse_create_person(name="Owner friend"),
    )
    other_person = await service.create_person(
        OTHER_USER_ID,
        parse_create_person(name="Other friend"),
    )

    with pytest.raises(LedgerNotFoundError) as hidden_person:
        await service.create_receivable(
            OWNER_ID,
            parse_create_obligation(
                person_id=other_person.id,
                amount="1.0000",
                currency="INR",
                description="Hidden person",
                issued_date=date(2026, 7, 20),
            ),
        )
    assert hidden_person.value.code == "PERSON_NOT_FOUND"

    with pytest.raises(LedgerNotFoundError) as hidden_transaction:
        await service.create_payable(
            OWNER_ID,
            parse_create_obligation(
                person_id=owner_person.id,
                amount="1.0000",
                currency="INR",
                description="Hidden transaction",
                issued_date=date(2026, 7, 20),
                transaction_id=OTHER_TRANSACTION_ID,
            ),
        )
    assert hidden_transaction.value.code == "TRANSACTION_NOT_FOUND"

    other_receivable = await service.create_receivable(
        OTHER_USER_ID,
        parse_create_obligation(
            person_id=other_person.id,
            amount="50.0000",
            currency="INR",
            description="Other owner's debt",
            issued_date=date(2026, 7, 20),
        ),
    )
    other_settlement = await service.settle_receivable(
        OTHER_USER_ID,
        other_receivable.id,
        parse_settlement(amount="10.0000", currency="INR", settled_at=NOW),
    )

    with pytest.raises(LedgerNotFoundError) as hidden_obligation:
        await service.get_receivable(OWNER_ID, other_receivable.id)
    assert hidden_obligation.value.code == "RECEIVABLE_NOT_FOUND"

    with pytest.raises(LedgerNotFoundError) as hidden_settlement_target:
        await service.settle_receivable(
            OWNER_ID,
            other_receivable.id,
            parse_settlement(amount="1.0000", currency="INR", settled_at=NOW),
        )
    assert hidden_settlement_target.value.code == "RECEIVABLE_NOT_FOUND"

    with pytest.raises(LedgerNotFoundError) as hidden_settlement:
        await service.get_settlement(OWNER_ID, other_settlement.settlement.id)
    assert hidden_settlement.value.code == "SETTLEMENT_NOT_FOUND"


@pytest.mark.database
@pytest.mark.asyncio
async def test_cancellation_and_totals_are_exact_per_currency(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = _service(isolated_database)
    person = await service.create_person(
        OWNER_ID,
        parse_create_person(name="Neha"),
    )
    receivable_inr = await service.create_receivable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="100.0000",
            currency="INR",
            description="INR receivable",
            issued_date=date(2026, 7, 20),
        ),
    )
    await service.settle_receivable(
        OWNER_ID,
        receivable_inr.id,
        parse_settlement(amount="25.0000", currency="INR", settled_at=NOW),
    )
    cancelled = await service.create_receivable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="50.0000",
            currency="INR",
            description="Cancelled receivable",
            issued_date=date(2026, 7, 20),
        ),
    )
    cancelled = await service.cancel_receivable(OWNER_ID, cancelled.id)
    receivable_usd = await service.create_receivable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="10.0000",
            currency="USD",
            description="USD receivable",
            issued_date=date(2026, 7, 20),
        ),
    )
    payable_inr = await service.create_payable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="30.0000",
            currency="INR",
            description="INR payable",
            issued_date=date(2026, 7, 20),
        ),
    )
    payable_usd = await service.create_payable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="4.0000",
            currency="USD",
            description="USD payable",
            issued_date=date(2026, 7, 20),
        ),
    )
    partial_payable = await service.settle_payable(
        OWNER_ID,
        payable_usd.id,
        parse_settlement(amount="1.0000", currency="USD", settled_at=NOW),
    )
    paid_payable = await service.create_payable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="20.0000",
            currency="INR",
            description="Paid payable",
            issued_date=date(2026, 7, 20),
        ),
    )
    paid_payable = (
        await service.settle_payable(
            OWNER_ID,
            paid_payable.id,
            parse_settlement(amount="20.0000", currency="INR", settled_at=NOW),
        )
    ).obligation
    cancelled_payable = await service.create_payable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="2.0000",
            currency="USD",
            description="Cancelled payable",
            issued_date=date(2026, 7, 20),
        ),
    )
    cancelled_payable = await service.cancel_payable(OWNER_ID, cancelled_payable.id)

    assert cancelled.settlement_status is ObligationStatus.CANCELLED
    assert cancelled.outstanding_amount == Decimal("0.0000")
    assert partial_payable.obligation.settlement_status is ObligationStatus.PARTIALLY_PAID
    assert paid_payable.settlement_status is ObligationStatus.PAID
    assert paid_payable.outstanding_amount == Decimal("0.0000")
    assert cancelled_payable.settlement_status is ObligationStatus.CANCELLED
    assert cancelled_payable.outstanding_amount == Decimal("0.0000")
    with pytest.raises(LedgerConflictError) as cancelled_settlement:
        await service.settle_receivable(
            OWNER_ID,
            cancelled.id,
            parse_settlement(amount="1.0000", currency="INR", settled_at=NOW),
        )
    assert cancelled_settlement.value.code == "OBLIGATION_CANCELLED"

    totals = await service.outstanding_totals(OWNER_ID)
    assert [(row.currency, row.receivable, row.payable, row.net_exposure) for row in totals] == [
        ("INR", Decimal("75.0000"), Decimal("30.0000"), Decimal("45.0000")),
        ("USD", Decimal("10.0000"), Decimal("3.0000"), Decimal("7.0000")),
    ]
    assert receivable_usd.outstanding_amount == Decimal("10.0000")
    assert payable_inr.outstanding_amount == Decimal("30.0000")


@pytest.mark.database
@pytest.mark.asyncio
async def test_competing_settlements_are_serialized_by_obligation_lock(
    isolated_database: Database,
) -> None:
    await _seed_owners(isolated_database)
    service = _service(isolated_database)
    person = await service.create_person(
        OWNER_ID,
        parse_create_person(name="Concurrent payer"),
    )
    payable = await service.create_payable(
        OWNER_ID,
        parse_create_obligation(
            person_id=person.id,
            amount="100.0000",
            currency="INR",
            description="Concurrent settlement",
            issued_date=date(2026, 7, 20),
        ),
    )
    command = parse_settlement(amount="60.0000", currency="INR", settled_at=NOW)

    results = await asyncio.gather(
        service.settle_payable(OWNER_ID, payable.id, command),
        service.settle_payable(OWNER_ID, payable.id, command),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, SettlementResult)]
    conflicts = [result for result in results if isinstance(result, LedgerConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code == "SETTLEMENT_EXCEEDS_OUTSTANDING"

    current = await service.get_payable(OWNER_ID, payable.id)
    assert current.settled_amount == Decimal("60.0000")
    assert current.outstanding_amount == Decimal("40.0000")
    assert current.settlement_status is ObligationStatus.PARTIALLY_PAID
