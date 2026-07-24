"""Immutable owner-scoped values for people and obligations."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domain.enums import ObligationStatus


class ObligationKind(StrEnum):
    """Direction of an interpersonal obligation."""

    RECEIVABLE = "receivable"
    PAYABLE = "payable"


@dataclass(frozen=True, slots=True)
class PersonView:
    """A person visible only inside one owner's ledger."""

    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class ObligationView:
    """Exact principal, settlement, and effective status for one obligation."""

    id: UUID
    kind: ObligationKind
    person_id: UUID
    person_name: str
    amount: Decimal
    settled_amount: Decimal
    outstanding_amount: Decimal
    currency: str
    description: str
    issued_date: date
    due_date: date | None
    settlement_status: ObligationStatus
    effective_status: ObligationStatus
    transaction_id: UUID | None


@dataclass(frozen=True, slots=True)
class SettlementView:
    """One immutable settlement owned by the current principal."""

    id: UUID
    kind: ObligationKind
    obligation_id: UUID
    amount: Decimal
    currency: str
    settled_at: datetime
    transaction_id: UUID | None
    note: str | None


@dataclass(frozen=True, slots=True)
class SettlementResult:
    """The immutable settlement and resulting obligation state."""

    settlement: SettlementView
    obligation: ObligationView


@dataclass(frozen=True, slots=True)
class OutstandingByCurrency:
    """Exact current exposure without cross-currency conversion."""

    currency: str
    receivable: Decimal
    payable: Decimal
    net_exposure: Decimal
