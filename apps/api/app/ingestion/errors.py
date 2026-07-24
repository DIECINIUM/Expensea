"""Stable content-safe ingestion failures."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IngestionError(Exception):
    """Base ingestion failure with a log/API-safe code and message."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class ConnectorContentError(IngestionError):
    """A connector envelope cannot satisfy its declared contract."""


class IngestionConflictError(IngestionError):
    """Persisted identity or state conflicts with the attempted operation."""


class ConnectorUnavailableError(IngestionError):
    """A connector cannot currently fetch authorized source data."""
