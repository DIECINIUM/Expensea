"""Deterministic receipt connector used to prove ingestion semantics."""

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from app.connectors.contracts import (
    ConnectorAuthorization,
    ConnectorBatch,
    ConnectorDescriptor,
    ConnectorEnvelope,
    ConnectorHealth,
    ConnectorHealthStatus,
)
from app.domain.enums import ConnectorType
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.errors import ConnectorContentError


class MockReceiptConnector:
    """In-memory deterministic source with a resumable offset cursor."""

    _descriptor = ConnectorDescriptor(
        key=ConnectorType.MOCK_RECEIPT,
        display_name="Mock receipts",
        authorization=ConnectorAuthorization.NONE,
        capabilities=("receipts", "transactions", "recurring-hints"),
    )

    def __init__(self, events: Iterable[ConnectorEnvelope]) -> None:
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
                message="The mock connector cursor is invalid.",
            )
        events = self._events[raw_offset:]
        return ConnectorBatch(
            events=events,
            next_cursor={"offset": len(self._events)},
        )

    def normalize(self, envelope: ConnectorEnvelope) -> NormalizedFinancialEventV1:
        values = dict(envelope.payload)
        values.setdefault("occurred_at", envelope.occurred_at)
        try:
            return NormalizedFinancialEventV1.model_validate(values)
        except ValidationError as exc:
            raise ConnectorContentError(
                code="INVALID_NORMALIZED_EVENT",
                message="The receipt could not be normalized safely.",
            ) from exc
