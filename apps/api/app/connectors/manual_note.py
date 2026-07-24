"""Authenticated informal-note connector feeding the shared ingestion boundary."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.connectors.contracts import (
    ConnectorAuthorization,
    ConnectorBatch,
    ConnectorDescriptor,
    ConnectorEnvelope,
    ConnectorHealth,
    ConnectorHealthStatus,
)
from app.domain.enums import ConnectorType, NormalizedEventKind
from app.domain.normalization import normalize_display_text
from app.ingestion.contracts import MAX_TAG_LENGTH, MAX_TAGS, NormalizedFinancialEventV1
from app.ingestion.errors import ConnectorContentError

MAX_MANUAL_NOTE_CHARS = 8_000


class ManualNoteConnector:
    """Convert explicit user notes into immutable raw events before AI use."""

    _descriptor = ConnectorDescriptor(
        key=ConnectorType.MANUAL_NOTE,
        display_name="Manual financial notes",
        authorization=ConnectorAuthorization.NONE,
        capabilities=("informal-notes", "labels"),
    )

    def __init__(self, events: Iterable[ConnectorEnvelope] = ()) -> None:
        self._events = tuple(events)

    @property
    def descriptor(self) -> ConnectorDescriptor:
        return self._descriptor

    async def health(self) -> ConnectorHealth:
        return ConnectorHealth(status=ConnectorHealthStatus.HEALTHY)

    async def fetch(self, cursor: dict[str, Any]) -> ConnectorBatch:
        raw_offset = cursor.get("offset", 0)
        if not isinstance(raw_offset, int) or raw_offset < 0:
            raise ConnectorContentError(
                code="INVALID_CONNECTOR_CURSOR",
                message="The manual-note connector cursor is invalid.",
            )
        return ConnectorBatch(
            events=self._events[raw_offset:],
            next_cursor={"offset": len(self._events)},
        )

    def normalize(self, envelope: ConnectorEnvelope) -> NormalizedFinancialEventV1:
        note = envelope.payload.get("extraction_text")
        tags = envelope.payload.get("labels", [])
        description = note[:200] if isinstance(note, str) else "Manual financial note"
        return NormalizedFinancialEventV1(
            event_kind=NormalizedEventKind.UNKNOWN,
            description=description,
            occurred_at=envelope.occurred_at,
            tags=tuple(tag for tag in tags if isinstance(tag, str)),
            confidence=None,
        )


def create_manual_note_envelope(
    note: str,
    *,
    source_timestamp: datetime,
    note_id: UUID | None = None,
    labels: Iterable[str] = (),
) -> ConnectorEnvelope:
    """Validate and minimize one authenticated note for durable ingestion."""
    normalized_note = normalize_display_text(note)
    if not normalized_note:
        raise ConnectorContentError(
            code="EMPTY_FINANCIAL_NOTE",
            message="The financial note cannot be blank.",
        )
    if len(normalized_note) > MAX_MANUAL_NOTE_CHARS:
        raise ConnectorContentError(
            code="FINANCIAL_NOTE_TOO_LONG",
            message="The financial note exceeds the ingestion size limit.",
        )
    if source_timestamp.tzinfo is None or source_timestamp.utcoffset() is None:
        raise ConnectorContentError(
            code="INVALID_SOURCE_TIMESTAMP",
            message="The note source timestamp must include a timezone offset.",
        )

    normalized_labels: list[str] = []
    seen: set[str] = set()
    for raw_label in labels:
        label = normalize_display_text(raw_label)
        if not label:
            continue
        if len(label) > MAX_TAG_LENGTH:
            raise ConnectorContentError(
                code="INVALID_NOTE_LABEL",
                message="A financial note label exceeds the size limit.",
            )
        lookup = label.casefold()
        if lookup not in seen:
            seen.add(lookup)
            normalized_labels.append(label)
        if len(normalized_labels) == MAX_TAGS:
            break

    event_id = note_id or uuid4()
    return ConnectorEnvelope(
        external_event_id=f"manual:{event_id}",
        event_type="manual_financial_note",
        occurred_at=source_timestamp,
        payload={
            "extraction_text": normalized_note,
            "labels": normalized_labels,
        },
        locator={"noteId": str(event_id)},
        evidence_excerpt=normalized_note[:500],
    )
