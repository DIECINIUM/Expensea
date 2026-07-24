"""Google Keep consumer-note import through official Takeout JSON exports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

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

MAX_KEEP_DOCUMENT_BYTES = 65_536
MAX_KEEP_NOTE_CHARS = 8_000


class GoogleKeepTakeoutConnector:
    """Import minimized note fields without scraping or retaining attachments."""

    _descriptor = ConnectorDescriptor(
        key=ConnectorType.GOOGLE_KEEP_TAKEOUT,
        display_name="Google Keep Takeout",
        authorization=ConnectorAuthorization.USER_EXPORT,
        capabilities=("informal-notes", "labels"),
    )

    def __init__(self, events: Iterable[ConnectorEnvelope]) -> None:
        self._events = tuple(events)

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[tuple[str, bytes | str]],
    ) -> GoogleKeepTakeoutConnector:
        events: list[ConnectorEnvelope] = []
        for filename, content in documents:
            envelope = parse_keep_takeout_document(filename, content)
            if envelope is not None:
                events.append(envelope)
        return cls(events)

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
                message="The Google Keep import cursor is invalid.",
            )
        return ConnectorBatch(
            events=self._events[raw_offset:],
            next_cursor={"offset": len(self._events)},
        )

    def normalize(self, envelope: ConnectorEnvelope) -> NormalizedFinancialEventV1:
        title = _optional_text(envelope.payload.get("title"))
        note_text = _optional_text(envelope.payload.get("note_text"))
        tags_value = envelope.payload.get("labels", [])
        tags = ["google-keep"]
        if isinstance(tags_value, list):
            tags.extend(item for item in tags_value if isinstance(item, str))
        description = title or (note_text[:200] if note_text else "Google Keep financial note")
        return NormalizedFinancialEventV1(
            event_kind=NormalizedEventKind.UNKNOWN,
            description=description,
            occurred_at=envelope.occurred_at,
            tags=tuple(tags),
            confidence=None,
        )


def parse_keep_takeout_document(
    filename: str,
    content: bytes | str,
) -> ConnectorEnvelope | None:
    """Parse supported note JSON fields and ignore attachment metadata/content."""
    encoded = content.encode("utf-8") if isinstance(content, str) else content
    if len(encoded) > MAX_KEEP_DOCUMENT_BYTES:
        raise ConnectorContentError(
            code="KEEP_DOCUMENT_TOO_LARGE",
            message="A Google Keep export document exceeds the import size limit.",
        )
    try:
        document = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConnectorContentError(
            code="KEEP_DOCUMENT_INVALID",
            message="A Google Keep export document is not valid JSON.",
        ) from exc
    if not isinstance(document, dict):
        raise ConnectorContentError(
            code="KEEP_DOCUMENT_INVALID",
            message="A Google Keep export document must contain one note object.",
        )
    if document.get("isTrashed") is True:
        return None

    title = _optional_text(document.get("title"))
    text_content = _optional_text(document.get("textContent"))
    list_text = _list_content_text(document.get("listContent"))
    note_text = normalize_display_text(
        "\n".join(item for item in [text_content, list_text] if item)
    )
    note_text = note_text[:MAX_KEEP_NOTE_CHARS]
    if not title and not note_text:
        return None

    labels = _labels(document.get("labels"))
    occurred_at = _keep_timestamp(document)
    filename_hash = hashlib.sha256(filename.encode("utf-8")).hexdigest()
    extraction_text = normalize_display_text("\n".join(item for item in [title, note_text] if item))
    return ConnectorEnvelope(
        external_event_id=f"takeout:{filename_hash}",
        event_type="google_keep_note",
        occurred_at=occurred_at,
        payload={
            "title": title,
            "note_text": note_text,
            "extraction_text": extraction_text[:MAX_KEEP_NOTE_CHARS],
            "labels": labels,
        },
        locator={"exportFileHash": filename_hash},
        evidence_excerpt=extraction_text[:500],
    )


def _list_content_text(value: object) -> str:
    if not isinstance(value, list):
        return ""
    items: list[str] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        text = _optional_text(raw_item.get("text"))
        if not text:
            continue
        prefix = "[x]" if raw_item.get("isChecked") is True else "[ ]"
        items.append(f"{prefix} {text}")
    return "\n".join(items)


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for raw_label in value:
        if not isinstance(raw_label, dict):
            continue
        label = _optional_text(raw_label.get("name"))
        if not label:
            continue
        label = label[:MAX_TAG_LENGTH]
        lookup = label.casefold()
        if lookup not in seen:
            seen.add(lookup)
            labels.append(label)
        if len(labels) == MAX_TAGS - 1:
            break
    return labels


def _keep_timestamp(document: dict[str, Any]) -> datetime | None:
    for key in ("userEditedTimestampUsec", "createdTimestampUsec"):
        raw_value = document.get(key)
        if raw_value is None:
            continue
        try:
            return datetime.fromtimestamp(int(raw_value) / 1_000_000, tz=UTC)
        except (OverflowError, TypeError, ValueError):
            continue
    return None


def _optional_text(value: object) -> str:
    return normalize_display_text(value) if isinstance(value, str) else ""
