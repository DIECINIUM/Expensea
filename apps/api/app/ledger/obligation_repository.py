"""Owner-scoped persistence for people, obligations, and settlements."""

from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Subquery

from app.domain.enums import ObligationStatus
from app.ledger.obligation_commands import (
    CreateObligationCommand,
    CreatePersonCommand,
    SettleObligationCommand,
)
from app.ledger.obligation_dto import (
    ObligationKind,
    ObligationView,
    OutstandingByCurrency,
    PersonView,
    SettlementView,
)
from app.models import (
    LedgerTransaction,
    ObligationSettlement,
    Payable,
    Person,
    Receivable,
    User,
)

_ZERO = Decimal("0.0000")


class ObligationRepository:
    """Persistence adapter whose private queries always require an owner key."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def owner_timezone(self, user_id: UUID) -> str | None:
        """Return the owner's IANA timezone without exposing another profile."""
        timezone_name = await self._session.scalar(select(User.timezone).where(User.id == user_id))
        return timezone_name

    async def create_person(
        self,
        user_id: UUID,
        command: CreatePersonCommand,
    ) -> PersonView | None:
        """Insert an owner-local person, returning None on a normalized duplicate."""
        person_id = uuid4()
        statement = (
            insert(Person)
            .values(
                id=person_id,
                user_id=user_id,
                name=command.name,
                normalized_name=command.normalized_name,
            )
            .on_conflict_do_nothing(constraint="uq_people_user_normalized_name")
            .returning(Person.id)
        )
        inserted_id = await self._session.scalar(statement)
        if inserted_id is None:
            return None
        return PersonView(id=inserted_id, name=command.name)

    async def list_people(self, user_id: UUID) -> tuple[PersonView, ...]:
        """List only people belonging to the supplied owner."""
        statement = (
            select(Person.id, Person.name)
            .where(Person.user_id == user_id)
            .order_by(Person.normalized_name.asc(), Person.id.asc())
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(PersonView(id=person_id, name=name) for person_id, name in rows)

    async def person_exists(self, user_id: UUID, person_id: UUID) -> bool:
        """Check an owner-person reference without revealing another tenant."""
        statement = select(Person.id).where(
            Person.user_id == user_id,
            Person.id == person_id,
        )
        return await self._session.scalar(statement) is not None

    async def transaction_exists(self, user_id: UUID, transaction_id: UUID) -> bool:
        """Check an owner-transaction reference without revealing another tenant."""
        statement = select(LedgerTransaction.id).where(
            LedgerTransaction.user_id == user_id,
            LedgerTransaction.id == transaction_id,
        )
        return await self._session.scalar(statement) is not None

    async def create_receivable(
        self,
        user_id: UUID,
        command: CreateObligationCommand,
        *,
        as_of: date,
    ) -> ObligationView:
        """Insert a validated receivable."""
        receivable = Receivable(
            user_id=user_id,
            person_id=command.person_id,
            amount=command.amount,
            currency=command.currency,
            description=command.description,
            issued_date=command.issued_date,
            due_date=command.due_date,
            transaction_id=command.transaction_id,
        )
        self._session.add(receivable)
        await self._session.flush()
        projected = await self.get_receivable(user_id, receivable.id, as_of=as_of)
        if projected is None:
            msg = "Inserted receivable was not visible in its owner scope"
            raise RuntimeError(msg)
        return projected

    async def create_payable(
        self,
        user_id: UUID,
        command: CreateObligationCommand,
        *,
        as_of: date,
    ) -> ObligationView:
        """Insert a validated payable."""
        payable = Payable(
            user_id=user_id,
            person_id=command.person_id,
            amount=command.amount,
            currency=command.currency,
            description=command.description,
            issued_date=command.issued_date,
            due_date=command.due_date,
            transaction_id=command.transaction_id,
        )
        self._session.add(payable)
        await self._session.flush()
        projected = await self.get_payable(user_id, payable.id, as_of=as_of)
        if projected is None:
            msg = "Inserted payable was not visible in its owner scope"
            raise RuntimeError(msg)
        return projected

    async def get_receivable(
        self,
        user_id: UUID,
        receivable_id: UUID,
        *,
        as_of: date,
    ) -> ObligationView | None:
        """Project one owner-scoped receivable with its exact settled total."""
        settled = _receivable_settled_subquery()
        statement = (
            select(
                Receivable,
                Person.name,
                func.coalesce(settled.c.settled_amount, _ZERO),
            )
            .join(
                Person,
                and_(
                    Person.id == Receivable.person_id,
                    Person.user_id == Receivable.user_id,
                ),
            )
            .outerjoin(settled, settled.c.obligation_id == Receivable.id)
            .where(
                Receivable.user_id == user_id,
                Receivable.id == receivable_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        receivable, person_name, settled_amount = row
        return _obligation_view(
            receivable,
            kind=ObligationKind.RECEIVABLE,
            person_name=person_name,
            settled_amount=Decimal(settled_amount),
            as_of=as_of,
        )

    async def get_payable(
        self,
        user_id: UUID,
        payable_id: UUID,
        *,
        as_of: date,
    ) -> ObligationView | None:
        """Project one owner-scoped payable with its exact settled total."""
        settled = _payable_settled_subquery()
        statement = (
            select(
                Payable,
                Person.name,
                func.coalesce(settled.c.settled_amount, _ZERO),
            )
            .join(
                Person,
                and_(
                    Person.id == Payable.person_id,
                    Person.user_id == Payable.user_id,
                ),
            )
            .outerjoin(settled, settled.c.obligation_id == Payable.id)
            .where(
                Payable.user_id == user_id,
                Payable.id == payable_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        payable, person_name, settled_amount = row
        return _obligation_view(
            payable,
            kind=ObligationKind.PAYABLE,
            person_name=person_name,
            settled_amount=Decimal(settled_amount),
            as_of=as_of,
        )

    async def list_receivables(
        self,
        user_id: UUID,
        *,
        as_of: date,
    ) -> tuple[ObligationView, ...]:
        """List owner receivables newest first."""
        settled = _receivable_settled_subquery()
        statement = (
            select(
                Receivable,
                Person.name,
                func.coalesce(settled.c.settled_amount, _ZERO),
            )
            .join(
                Person,
                and_(
                    Person.id == Receivable.person_id,
                    Person.user_id == Receivable.user_id,
                ),
            )
            .outerjoin(settled, settled.c.obligation_id == Receivable.id)
            .where(Receivable.user_id == user_id)
            .order_by(Receivable.issued_date.desc(), Receivable.id.desc())
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(
            _obligation_view(
                obligation,
                kind=ObligationKind.RECEIVABLE,
                person_name=person_name,
                settled_amount=Decimal(settled_amount),
                as_of=as_of,
            )
            for obligation, person_name, settled_amount in rows
        )

    async def list_payables(
        self,
        user_id: UUID,
        *,
        as_of: date,
    ) -> tuple[ObligationView, ...]:
        """List owner payables newest first."""
        settled = _payable_settled_subquery()
        statement = (
            select(
                Payable,
                Person.name,
                func.coalesce(settled.c.settled_amount, _ZERO),
            )
            .join(
                Person,
                and_(
                    Person.id == Payable.person_id,
                    Person.user_id == Payable.user_id,
                ),
            )
            .outerjoin(settled, settled.c.obligation_id == Payable.id)
            .where(Payable.user_id == user_id)
            .order_by(Payable.issued_date.desc(), Payable.id.desc())
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(
            _obligation_view(
                obligation,
                kind=ObligationKind.PAYABLE,
                person_name=person_name,
                settled_amount=Decimal(settled_amount),
                as_of=as_of,
            )
            for obligation, person_name, settled_amount in rows
        )

    async def lock_receivable(
        self,
        user_id: UUID,
        receivable_id: UUID,
    ) -> Receivable | None:
        """Lock one owner-scoped receivable before settlement state changes."""
        statement = (
            select(Receivable)
            .where(
                Receivable.user_id == user_id,
                Receivable.id == receivable_id,
            )
            .with_for_update()
        )
        return cast(Receivable | None, await self._session.scalar(statement))

    async def lock_payable(
        self,
        user_id: UUID,
        payable_id: UUID,
    ) -> Payable | None:
        """Lock one owner-scoped payable before settlement state changes."""
        statement = (
            select(Payable)
            .where(
                Payable.user_id == user_id,
                Payable.id == payable_id,
            )
            .with_for_update()
        )
        return cast(Payable | None, await self._session.scalar(statement))

    async def receivable_settled_amount(
        self,
        user_id: UUID,
        receivable_id: UUID,
    ) -> Decimal:
        """Sum immutable settlement history after the obligation lock is held."""
        statement = select(func.coalesce(func.sum(ObligationSettlement.amount), _ZERO)).where(
            ObligationSettlement.user_id == user_id,
            ObligationSettlement.receivable_id == receivable_id,
        )
        return Decimal((await self._session.execute(statement)).scalar_one())

    async def payable_settled_amount(
        self,
        user_id: UUID,
        payable_id: UUID,
    ) -> Decimal:
        """Sum immutable settlement history after the obligation lock is held."""
        statement = select(func.coalesce(func.sum(ObligationSettlement.amount), _ZERO)).where(
            ObligationSettlement.user_id == user_id,
            ObligationSettlement.payable_id == payable_id,
        )
        return Decimal((await self._session.execute(statement)).scalar_one())

    async def add_receivable_settlement(
        self,
        user_id: UUID,
        receivable_id: UUID,
        command: SettleObligationCommand,
    ) -> SettlementView:
        """Append a settlement referencing exactly one owner receivable."""
        settlement = ObligationSettlement(
            user_id=user_id,
            receivable_id=receivable_id,
            amount=command.amount,
            currency=command.currency,
            settled_at=command.settled_at,
            transaction_id=command.transaction_id,
            note=command.note,
        )
        self._session.add(settlement)
        await self._session.flush()
        return _settlement_view(settlement)

    async def add_payable_settlement(
        self,
        user_id: UUID,
        payable_id: UUID,
        command: SettleObligationCommand,
    ) -> SettlementView:
        """Append a settlement referencing exactly one owner payable."""
        settlement = ObligationSettlement(
            user_id=user_id,
            payable_id=payable_id,
            amount=command.amount,
            currency=command.currency,
            settled_at=command.settled_at,
            transaction_id=command.transaction_id,
            note=command.note,
        )
        self._session.add(settlement)
        await self._session.flush()
        return _settlement_view(settlement)

    async def get_settlement(
        self,
        user_id: UUID,
        settlement_id: UUID,
    ) -> SettlementView | None:
        """Return a settlement only inside its owner scope."""
        statement = select(ObligationSettlement).where(
            ObligationSettlement.user_id == user_id,
            ObligationSettlement.id == settlement_id,
        )
        settlement = await self._session.scalar(statement)
        return _settlement_view(settlement) if settlement is not None else None

    async def outstanding_totals(
        self,
        user_id: UUID,
    ) -> tuple[OutstandingByCurrency, ...]:
        """Return exact receivable/payable exposure grouped by currency."""
        receivables = await self._receivable_totals(user_id)
        payables = await self._payable_totals(user_id)
        currencies = sorted(receivables.keys() | payables.keys())
        return tuple(
            OutstandingByCurrency(
                currency=currency,
                receivable=receivables.get(currency, _ZERO),
                payable=payables.get(currency, _ZERO),
                net_exposure=receivables.get(currency, _ZERO) - payables.get(currency, _ZERO),
            )
            for currency in currencies
        )

    async def flush(self) -> None:
        """Flush an obligation status transition before projecting it."""
        await self._session.flush()

    async def _receivable_totals(self, user_id: UUID) -> dict[str, Decimal]:
        settled = _receivable_settled_subquery()
        outstanding = case(
            (Receivable.status == ObligationStatus.CANCELLED, _ZERO),
            else_=Receivable.amount - func.coalesce(settled.c.settled_amount, _ZERO),
        )
        statement = (
            select(Receivable.currency, func.sum(outstanding))
            .outerjoin(settled, settled.c.obligation_id == Receivable.id)
            .where(Receivable.user_id == user_id)
            .group_by(Receivable.currency)
        )
        rows = (await self._session.execute(statement)).all()
        return {currency: Decimal(amount) for currency, amount in rows}

    async def _payable_totals(self, user_id: UUID) -> dict[str, Decimal]:
        settled = _payable_settled_subquery()
        outstanding = case(
            (Payable.status == ObligationStatus.CANCELLED, _ZERO),
            else_=Payable.amount - func.coalesce(settled.c.settled_amount, _ZERO),
        )
        statement = (
            select(Payable.currency, func.sum(outstanding))
            .outerjoin(settled, settled.c.obligation_id == Payable.id)
            .where(Payable.user_id == user_id)
            .group_by(Payable.currency)
        )
        rows = (await self._session.execute(statement)).all()
        return {currency: Decimal(amount) for currency, amount in rows}


def _receivable_settled_subquery() -> Subquery:
    return (
        select(
            ObligationSettlement.receivable_id.label("obligation_id"),
            func.sum(ObligationSettlement.amount).label("settled_amount"),
        )
        .where(ObligationSettlement.receivable_id.is_not(None))
        .group_by(ObligationSettlement.receivable_id)
        .subquery()
    )


def _payable_settled_subquery() -> Subquery:
    return (
        select(
            ObligationSettlement.payable_id.label("obligation_id"),
            func.sum(ObligationSettlement.amount).label("settled_amount"),
        )
        .where(ObligationSettlement.payable_id.is_not(None))
        .group_by(ObligationSettlement.payable_id)
        .subquery()
    )


def _obligation_view(
    obligation: Receivable | Payable,
    *,
    kind: ObligationKind,
    person_name: str,
    settled_amount: Decimal,
    as_of: date,
) -> ObligationView:
    remaining_principal = obligation.amount - settled_amount
    outstanding = _ZERO if obligation.status == ObligationStatus.CANCELLED else remaining_principal
    effective_status = obligation.status
    if (
        obligation.status in {ObligationStatus.OPEN, ObligationStatus.PARTIALLY_PAID}
        and obligation.due_date is not None
        and obligation.due_date < as_of
        and outstanding > 0
    ):
        effective_status = ObligationStatus.OVERDUE
    return ObligationView(
        id=obligation.id,
        kind=kind,
        person_id=obligation.person_id,
        person_name=person_name,
        amount=obligation.amount,
        settled_amount=settled_amount,
        outstanding_amount=outstanding,
        currency=obligation.currency,
        description=obligation.description,
        issued_date=obligation.issued_date,
        due_date=obligation.due_date,
        settlement_status=obligation.status,
        effective_status=effective_status,
        transaction_id=obligation.transaction_id,
    )


def _settlement_view(settlement: ObligationSettlement) -> SettlementView:
    if settlement.receivable_id is not None:
        kind = ObligationKind.RECEIVABLE
        obligation_id = settlement.receivable_id
    elif settlement.payable_id is not None:
        kind = ObligationKind.PAYABLE
        obligation_id = settlement.payable_id
    else:
        msg = "Settlement does not reference an obligation"
        raise RuntimeError(msg)
    return SettlementView(
        id=settlement.id,
        kind=kind,
        obligation_id=obligation_id,
        amount=settlement.amount,
        currency=settlement.currency,
        settled_at=settlement.settled_at,
        transaction_id=settlement.transaction_id,
        note=settlement.note,
    )
