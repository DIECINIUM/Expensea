"""Transactional owner-scoped workflows for people and obligations."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.db.session import Database
from app.domain.enums import ObligationStatus
from app.domain.money import validate_positive_money
from app.ledger.errors import (
    LedgerConflictError,
    LedgerNotFoundError,
    LedgerValidationError,
)
from app.ledger.obligation_commands import (
    CreateObligationCommand,
    CreatePersonCommand,
    SettleObligationCommand,
)
from app.ledger.obligation_dto import (
    ObligationView,
    OutstandingByCurrency,
    PersonView,
    SettlementResult,
    SettlementView,
)
from app.ledger.obligation_repository import ObligationRepository
from app.ledger.periods import parse_timezone
from app.models import Payable, Receivable

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ObligationService:
    """Use cases that keep ownership, money, and settlement state deterministic."""

    def __init__(self, database: Database, *, clock: Clock = _utc_now) -> None:
        self._database = database
        self._clock = clock

    async def create_person(
        self,
        user_id: UUID,
        command: CreatePersonCommand,
    ) -> PersonView:
        """Create one normalized owner-local person."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ObligationRepository(session)
            await self._require_owner(repository, user_id)
            person = await repository.create_person(user_id, command)
            if person is None:
                raise LedgerConflictError(
                    code="PERSON_ALREADY_EXISTS",
                    message="A person with that name already exists.",
                    field="name",
                )
            return person

    async def list_people(self, user_id: UUID) -> tuple[PersonView, ...]:
        """Return only people belonging to the supplied owner."""
        async with self._database.session_factory()() as session:
            repository = ObligationRepository(session)
            await self._require_owner(repository, user_id)
            return await repository.list_people(user_id)

    async def create_receivable(
        self,
        user_id: UUID,
        command: CreateObligationCommand,
    ) -> ObligationView:
        """Create principal another person owes the owner."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            await self._validate_create_references(repository, user_id, command)
            return await repository.create_receivable(user_id, command, as_of=as_of)

    async def create_payable(
        self,
        user_id: UUID,
        command: CreateObligationCommand,
    ) -> ObligationView:
        """Create principal the owner owes another person."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            await self._validate_create_references(repository, user_id, command)
            return await repository.create_payable(user_id, command, as_of=as_of)

    async def get_receivable(
        self,
        user_id: UUID,
        receivable_id: UUID,
    ) -> ObligationView:
        """Return one owner-scoped receivable."""
        async with self._database.session_factory()() as session:
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            receivable = await repository.get_receivable(
                user_id,
                receivable_id,
                as_of=as_of,
            )
        return self._require_receivable(receivable)

    async def get_payable(
        self,
        user_id: UUID,
        payable_id: UUID,
    ) -> ObligationView:
        """Return one owner-scoped payable."""
        async with self._database.session_factory()() as session:
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            payable = await repository.get_payable(user_id, payable_id, as_of=as_of)
        return self._require_payable(payable)

    async def list_receivables(self, user_id: UUID) -> tuple[ObligationView, ...]:
        """List only this owner's receivables."""
        async with self._database.session_factory()() as session:
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            return await repository.list_receivables(user_id, as_of=as_of)

    async def list_payables(self, user_id: UUID) -> tuple[ObligationView, ...]:
        """List only this owner's payables."""
        async with self._database.session_factory()() as session:
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            return await repository.list_payables(user_id, as_of=as_of)

    async def settle_receivable(
        self,
        user_id: UUID,
        receivable_id: UUID,
        command: SettleObligationCommand,
    ) -> SettlementResult:
        """Apply a serialized partial or full receivable settlement."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            receivable = self._require_receivable_model(
                await repository.lock_receivable(user_id, receivable_id)
            )
            await self._validate_settlement_reference(repository, user_id, command)
            settled = await repository.receivable_settled_amount(user_id, receivable_id)
            self._validate_settlement(receivable, command, settled)
            settlement = await repository.add_receivable_settlement(
                user_id,
                receivable_id,
                command,
            )
            receivable.status = self._next_status(
                principal=receivable.amount,
                settled=settled + command.amount,
            )
            await repository.flush()
            projected = self._require_receivable(
                await repository.get_receivable(user_id, receivable_id, as_of=as_of)
            )
            return SettlementResult(settlement=settlement, obligation=projected)

    async def settle_payable(
        self,
        user_id: UUID,
        payable_id: UUID,
        command: SettleObligationCommand,
    ) -> SettlementResult:
        """Apply a serialized partial or full payable settlement."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            payable = self._require_payable_model(
                await repository.lock_payable(user_id, payable_id)
            )
            await self._validate_settlement_reference(repository, user_id, command)
            settled = await repository.payable_settled_amount(user_id, payable_id)
            self._validate_settlement(payable, command, settled)
            settlement = await repository.add_payable_settlement(
                user_id,
                payable_id,
                command,
            )
            payable.status = self._next_status(
                principal=payable.amount,
                settled=settled + command.amount,
            )
            await repository.flush()
            projected = self._require_payable(
                await repository.get_payable(user_id, payable_id, as_of=as_of)
            )
            return SettlementResult(settlement=settlement, obligation=projected)

    async def cancel_receivable(
        self,
        user_id: UUID,
        receivable_id: UUID,
    ) -> ObligationView:
        """Cancel remaining receivable principal while preserving settlement history."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            receivable = self._require_receivable_model(
                await repository.lock_receivable(user_id, receivable_id)
            )
            self._cancel(receivable)
            await repository.flush()
            return self._require_receivable(
                await repository.get_receivable(user_id, receivable_id, as_of=as_of)
            )

    async def cancel_payable(
        self,
        user_id: UUID,
        payable_id: UUID,
    ) -> ObligationView:
        """Cancel remaining payable principal while preserving settlement history."""
        async with self._database.session_factory()() as session, session.begin():
            repository = ObligationRepository(session)
            as_of = await self._owner_today(repository, user_id)
            payable = self._require_payable_model(
                await repository.lock_payable(user_id, payable_id)
            )
            self._cancel(payable)
            await repository.flush()
            return self._require_payable(
                await repository.get_payable(user_id, payable_id, as_of=as_of)
            )

    async def outstanding_totals(
        self,
        user_id: UUID,
    ) -> tuple[OutstandingByCurrency, ...]:
        """Return exact open exposure for each currency."""
        async with self._database.session_factory()() as session:
            repository = ObligationRepository(session)
            await self._require_owner(repository, user_id)
            return await repository.outstanding_totals(user_id)

    async def get_settlement(
        self,
        user_id: UUID,
        settlement_id: UUID,
    ) -> SettlementView:
        """Return one immutable settlement without leaking another tenant."""
        async with self._database.session_factory()() as session:
            settlement = await ObligationRepository(session).get_settlement(
                user_id,
                settlement_id,
            )
        if settlement is None:
            raise LedgerNotFoundError(
                code="SETTLEMENT_NOT_FOUND",
                message="The settlement was not found.",
            )
        return settlement

    async def _validate_create_references(
        self,
        repository: ObligationRepository,
        user_id: UUID,
        command: CreateObligationCommand,
    ) -> None:
        if not await repository.person_exists(user_id, command.person_id):
            raise LedgerNotFoundError(
                code="PERSON_NOT_FOUND",
                message="The person was not found.",
                field="personId",
            )
        if command.transaction_id is not None and not await repository.transaction_exists(
            user_id,
            command.transaction_id,
        ):
            raise LedgerNotFoundError(
                code="TRANSACTION_NOT_FOUND",
                message="The transaction was not found.",
                field="transactionId",
            )

    async def _validate_settlement_reference(
        self,
        repository: ObligationRepository,
        user_id: UUID,
        command: SettleObligationCommand,
    ) -> None:
        if command.transaction_id is not None and not await repository.transaction_exists(
            user_id,
            command.transaction_id,
        ):
            raise LedgerNotFoundError(
                code="TRANSACTION_NOT_FOUND",
                message="The transaction was not found.",
                field="transactionId",
            )

    async def _owner_today(
        self,
        repository: ObligationRepository,
        user_id: UUID,
    ) -> date:
        timezone_name = await self._require_owner(repository, user_id)
        return self._now().astimezone(parse_timezone(timezone_name)).date()

    async def _require_owner(
        self,
        repository: ObligationRepository,
        user_id: UUID,
    ) -> str:
        timezone_name = await repository.owner_timezone(user_id)
        if timezone_name is None:
            raise LedgerNotFoundError(
                code="PROFILE_NOT_FOUND",
                message="The ledger profile was not found.",
            )
        return timezone_name

    def _now(self) -> datetime:
        instant = self._clock()
        if instant.tzinfo is None or instant.utcoffset() is None:
            msg = "Obligation clock must return a timezone-aware instant"
            raise RuntimeError(msg)
        return instant.astimezone(UTC)

    @staticmethod
    def _validate_settlement(
        obligation: Receivable | Payable,
        command: SettleObligationCommand,
        already_settled: Decimal,
    ) -> None:
        try:
            validate_positive_money(command.amount)
        except ValueError:
            raise LedgerValidationError(
                code="INVALID_AMOUNT",
                message="Settlement amount must be positive and exact.",
                field="amount",
            ) from None
        if obligation.status == ObligationStatus.CANCELLED:
            raise LedgerConflictError(
                code="OBLIGATION_CANCELLED",
                message="A cancelled obligation cannot be settled.",
            )
        if obligation.status == ObligationStatus.PAID:
            raise LedgerConflictError(
                code="OBLIGATION_PAID",
                message="A paid obligation cannot be settled again.",
            )
        if command.currency != obligation.currency:
            raise LedgerValidationError(
                code="SETTLEMENT_CURRENCY_MISMATCH",
                message="Settlement currency must match the obligation currency.",
                field="currency",
            )
        outstanding = obligation.amount - already_settled
        if command.amount > outstanding:
            raise LedgerConflictError(
                code="SETTLEMENT_EXCEEDS_OUTSTANDING",
                message="Settlement amount exceeds the outstanding principal.",
                field="amount",
            )

    @staticmethod
    def _next_status(*, principal: Decimal, settled: Decimal) -> ObligationStatus:
        return ObligationStatus.PAID if settled == principal else ObligationStatus.PARTIALLY_PAID

    @staticmethod
    def _cancel(obligation: Receivable | Payable) -> None:
        if obligation.status == ObligationStatus.PAID:
            raise LedgerConflictError(
                code="OBLIGATION_PAID",
                message="A paid obligation cannot be cancelled.",
            )
        obligation.status = ObligationStatus.CANCELLED

    @staticmethod
    def _require_receivable(receivable: ObligationView | None) -> ObligationView:
        if receivable is None:
            raise LedgerNotFoundError(
                code="RECEIVABLE_NOT_FOUND",
                message="The receivable was not found.",
            )
        return receivable

    @staticmethod
    def _require_payable(payable: ObligationView | None) -> ObligationView:
        if payable is None:
            raise LedgerNotFoundError(
                code="PAYABLE_NOT_FOUND",
                message="The payable was not found.",
            )
        return payable

    @staticmethod
    def _require_receivable_model(receivable: Receivable | None) -> Receivable:
        if receivable is None:
            raise LedgerNotFoundError(
                code="RECEIVABLE_NOT_FOUND",
                message="The receivable was not found.",
            )
        return receivable

    @staticmethod
    def _require_payable_model(payable: Payable | None) -> Payable:
        if payable is None:
            raise LedgerNotFoundError(
                code="PAYABLE_NOT_FOUND",
                message="The payable was not found.",
            )
        return payable
