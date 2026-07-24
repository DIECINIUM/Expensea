"""Client-safe ledger failures."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LedgerError(Exception):
    """Base failure carrying a stable public code and bounded message."""

    code: str
    message: str
    field: str | None = None

    def __str__(self) -> str:
        return self.message


class LedgerValidationError(LedgerError):
    """A command violates a deterministic ledger invariant."""


class LedgerNotFoundError(LedgerError):
    """An entity is absent or unavailable to the current principal."""


class LedgerConflictError(LedgerError):
    """A command conflicts with the current ledger state."""


class InvalidCursorError(LedgerValidationError):
    """A pagination cursor cannot be decoded safely."""

    def __init__(self) -> None:
        super().__init__(
            code="INVALID_CURSOR",
            message="The pagination cursor is invalid or no longer supported.",
            field="after",
        )
