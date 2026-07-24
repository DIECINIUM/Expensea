"""Bounded user-authorized CSV import behind the shared connector contract."""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.connectors.contracts import (
    ConnectorAuthorization,
    ConnectorBatch,
    ConnectorDescriptor,
    ConnectorEnvelope,
    ConnectorHealth,
    ConnectorHealthStatus,
)
from app.domain.enums import ConnectorType
from app.domain.normalization import normalize_display_text
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.errors import ConnectorContentError

MAX_CSV_DOCUMENT_BYTES = 262_144
MAX_CSV_ROWS = 1_000
_REQUIRED_COLUMNS = frozenset({"event_kind", "description"})
_ALLOWED_COLUMNS = frozenset(
    {
        "external_id",
        "event_kind",
        "amount",
        "currency",
        "description",
        "occurred_at",
        "merchant_name",
        "counterparty",
        "category_hint",
        "tags",
        "confidence",
    }
)
_OPTIONAL_COLUMNS = _ALLOWED_COLUMNS - _REQUIRED_COLUMNS
_DATETIME_ADAPTER = TypeAdapter(datetime)


class CsvTransactionConnector:
    """Import explicit financial rows without provider-specific downstream code."""

    _descriptor = ConnectorDescriptor(
        key=ConnectorType.CSV_IMPORT,
        display_name="CSV transaction import",
        authorization=ConnectorAuthorization.USER_EXPORT,
        capabilities=("transactions", "batch-import", "tags"),
    )

    def __init__(self, events: Iterable[ConnectorEnvelope]) -> None:
        self._events = tuple(events)

    @classmethod
    def from_document(
        cls,
        filename: str,
        content: bytes | str,
    ) -> CsvTransactionConnector:
        return cls(parse_csv_document(filename, content))

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
                message="The CSV import cursor is invalid.",
            )
        return ConnectorBatch(
            events=self._events[raw_offset:],
            next_cursor={"offset": len(self._events)},
        )

    def normalize(self, envelope: ConnectorEnvelope) -> NormalizedFinancialEventV1:
        try:
            return NormalizedFinancialEventV1.model_validate(envelope.payload)
        except ValidationError as exc:
            raise ConnectorContentError(
                code="CSV_ROW_INVALID",
                message="A CSV row does not satisfy the normalized event contract.",
            ) from exc


def parse_csv_document(
    filename: str,
    content: bytes | str,
) -> tuple[ConnectorEnvelope, ...]:
    """Parse one strict UTF-8 CSV document into minimized replayable envelopes."""
    encoded = content.encode("utf-8") if isinstance(content, str) else content
    if len(encoded) > MAX_CSV_DOCUMENT_BYTES:
        raise ConnectorContentError(
            code="CSV_DOCUMENT_TOO_LARGE",
            message="The CSV document exceeds the 256 KiB import limit.",
        )
    try:
        decoded = encoded.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConnectorContentError(
            code="CSV_DOCUMENT_INVALID_ENCODING",
            message="The CSV document must use UTF-8 encoding.",
        ) from exc
    if "\x00" in decoded:
        raise ConnectorContentError(
            code="CSV_DOCUMENT_INVALID",
            message="The CSV document contains unsupported null bytes.",
        )

    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    columns = tuple(reader.fieldnames or ())
    if not columns or any(not column for column in columns):
        raise ConnectorContentError(
            code="CSV_HEADER_INVALID",
            message="The CSV document must include a non-empty header row.",
        )
    column_set = set(columns)
    if not _REQUIRED_COLUMNS.issubset(column_set):
        raise ConnectorContentError(
            code="CSV_REQUIRED_COLUMNS_MISSING",
            message="CSV rows require event_kind and description columns.",
        )
    if not column_set.issubset(_ALLOWED_COLUMNS):
        raise ConnectorContentError(
            code="CSV_COLUMNS_UNSUPPORTED",
            message="The CSV document includes unsupported columns.",
        )

    file_hash = hashlib.sha256(encoded).hexdigest()
    events: list[ConnectorEnvelope] = []
    try:
        for row_number, row in enumerate(reader, start=2):
            if row_number > MAX_CSV_ROWS + 1:
                raise ConnectorContentError(
                    code="CSV_ROW_LIMIT_EXCEEDED",
                    message=f"CSV imports cannot exceed {MAX_CSV_ROWS} data rows.",
                )
            events.append(_row_envelope(row, row_number=row_number, file_hash=file_hash))
    except csv.Error as exc:
        raise ConnectorContentError(
            code="CSV_DOCUMENT_INVALID",
            message="The CSV document could not be parsed safely.",
        ) from exc
    return tuple(events)


def _row_envelope(
    row: dict[str | None, str | None],
    *,
    row_number: int,
    file_hash: str,
) -> ConnectorEnvelope:
    if None in row:
        raise ConnectorContentError(
            code="CSV_ROW_COLUMN_MISMATCH",
            message=f"CSV row {row_number} has more values than declared columns.",
        )
    values = {
        key: normalize_display_text(value)
        for key, value in row.items()
        if key is not None and value is not None
    }
    event_kind = values.get("event_kind", "")
    description = values.get("description", "")
    if not event_kind or not description:
        raise ConnectorContentError(
            code="CSV_ROW_REQUIRED_VALUE_MISSING",
            message=f"CSV row {row_number} requires event_kind and description values.",
        )

    payload: dict[str, object] = {
        "event_kind": event_kind,
        "description": description,
    }
    for column in _OPTIONAL_COLUMNS - {"external_id", "occurred_at", "tags"}:
        value = values.get(column)
        if value:
            payload[column] = value
    tags = values.get("tags")
    if tags:
        payload["tags"] = [tag.strip() for tag in tags.split("|") if tag.strip()]

    occurred_at = _optional_datetime(values.get("occurred_at"), row_number=row_number)
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at
    external_id = values.get("external_id") or None
    return ConnectorEnvelope(
        external_event_id=external_id,
        event_type="csv_financial_event",
        occurred_at=occurred_at,
        payload=payload,
        locator={"fileHash": file_hash, "row": row_number},
        evidence_excerpt=description[:500],
    )


def _optional_datetime(value: str | None, *, row_number: int) -> datetime | None:
    if not value:
        return None
    try:
        parsed = _DATETIME_ADAPTER.validate_python(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (ValidationError, ValueError) as exc:
        raise ConnectorContentError(
            code="CSV_ROW_DATETIME_INVALID",
            message=f"CSV row {row_number} occurred_at must include a timezone offset.",
        ) from exc
