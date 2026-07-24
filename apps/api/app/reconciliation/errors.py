"""Content-safe reconciliation failures."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconciliationError(Exception):
    """Base owner-safe reconciliation error."""

    code: str
    message: str
    field: str | None = None

    def __str__(self) -> str:
        return self.message


class ReconciliationNotFoundError(ReconciliationError):
    """The owner-visible case or transaction was not found."""


class ReconciliationConflictError(ReconciliationError):
    """The requested reconciliation state transition is stale or invalid."""
