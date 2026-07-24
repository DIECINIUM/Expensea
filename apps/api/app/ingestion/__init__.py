"""Replay-safe provider-neutral financial ingestion."""

from app.ingestion.contracts import (
    NORMALIZED_EVENT_SCHEMA_VERSION,
    NormalizedFinancialEventV1,
)

__all__ = [
    "NORMALIZED_EVENT_SCHEMA_VERSION",
    "NormalizedFinancialEventV1",
]
