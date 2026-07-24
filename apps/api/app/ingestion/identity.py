"""Canonical source-content identity without retaining unnecessary data."""

import hashlib
import json
from typing import Any

from pydantic_core import PydanticSerializationError

from app.connectors.contracts import ConnectorEnvelope
from app.ingestion.errors import ConnectorContentError

MAX_ENVELOPE_BYTES = 32_768


def canonical_envelope(envelope: ConnectorEnvelope) -> dict[str, Any]:
    """Return the bounded JSON-compatible envelope used for hashing/storage."""
    try:
        serialized = envelope.model_dump(mode="json", exclude={"external_event_id"})
        encoded = json.dumps(
            serialized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (PydanticSerializationError, TypeError, ValueError) as exc:
        raise ConnectorContentError(
            code="INVALID_SOURCE_PAYLOAD",
            message="The source event is not valid JSON data.",
        ) from exc
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise ConnectorContentError(
            code="SOURCE_PAYLOAD_TOO_LARGE",
            message="The minimized source event exceeds the ingestion size limit.",
        )
    return serialized


def content_sha256(envelope: ConnectorEnvelope) -> str:
    """Hash canonical minimized content for fallback delivery identity."""
    serialized = canonical_envelope(envelope)
    encoded = json.dumps(
        serialized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def event_identity_key(
    envelope: ConnectorEnvelope,
    *,
    content_hash: str,
) -> str:
    """Prefer stable provider identity and fall back to exact canonical content."""
    if envelope.external_event_id is not None:
        return f"external:{envelope.external_event_id}"
    return f"sha256:{content_hash}"
