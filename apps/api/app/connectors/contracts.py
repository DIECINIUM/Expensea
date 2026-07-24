"""Provider adapter boundary for source fetch, health, and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import ConnectorType
from app.domain.normalization import normalize_display_text
from app.ingestion.contracts import NormalizedFinancialEventV1


class ConnectorAuthorization(StrEnum):
    """Authorization shape required by a connector."""

    NONE = "none"
    READ_ONLY_OAUTH = "read_only_oauth"
    USER_EXPORT = "user_export"


class ConnectorHealthStatus(StrEnum):
    """Content-safe source health states."""

    HEALTHY = "healthy"
    MISCONFIGURED = "misconfigured"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ConnectorDescriptor:
    """Stable metadata used by the registry and future connection UI."""

    key: ConnectorType
    display_name: str
    authorization: ConnectorAuthorization
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConnectorHealth:
    """A bounded health result that never includes credentials or source content."""

    status: ConnectorHealthStatus
    code: str | None = None


class ConnectorEnvelope(BaseModel):
    """Minimized provider envelope accepted by shared ingestion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    external_event_id: str | None = Field(default=None, max_length=255)
    event_type: str = Field(min_length=1, max_length=80)
    occurred_at: datetime | None = None
    payload: dict[str, Any]
    locator: dict[str, Any] = Field(default_factory=dict)
    evidence_excerpt: str | None = Field(default=None, max_length=500)

    @field_validator("external_event_id", "event_type", "evidence_excerpt", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = normalize_display_text(value)
        return normalized or None

    @field_validator("event_type")
    @classmethod
    def require_event_type(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("event_type cannot be blank")
        return value

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ConnectorBatch:
    """One bounded fetch page and the cursor to persist after durable receipt."""

    events: tuple[ConnectorEnvelope, ...]
    next_cursor: dict[str, Any]


class Connector(Protocol):
    """Common behavior implemented by every source-specific adapter."""

    @property
    def descriptor(self) -> ConnectorDescriptor:
        """Return stable non-secret connector metadata."""
        ...

    async def health(self) -> ConnectorHealth:
        """Check adapter configuration without exposing private source data."""
        ...

    async def fetch(self, cursor: dict[str, Any]) -> ConnectorBatch:
        """Fetch a bounded page after the supplied persisted cursor."""
        ...

    def normalize(self, envelope: ConnectorEnvelope) -> NormalizedFinancialEventV1:
        """Convert one provider envelope into the versioned shared contract."""
        ...
