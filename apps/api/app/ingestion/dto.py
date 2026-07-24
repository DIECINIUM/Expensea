"""Immutable ingestion service projections."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.domain.enums import ConnectorType, RawEventState, SourceConnectionStatus


@dataclass(frozen=True, slots=True)
class SourceConnectionView:
    """Non-secret source connection values needed by sync orchestration."""

    id: UUID
    connector_type: ConnectorType
    connection_key: str
    display_name: str
    status: SourceConnectionStatus
    cursor: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StoredRawEvent:
    """Identity result returned after race-safe raw-event insertion."""

    id: UUID
    created: bool
    content_sha256: str


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome for one source delivery."""

    raw_event_id: UUID
    normalized_event_id: UUID | None
    transaction_id: UUID | None
    state: RawEventState
    replayed: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectorSyncResult:
    """Results and durable connection identity for one connector page."""

    connection_id: UUID
    events: tuple[IngestionResult, ...]
