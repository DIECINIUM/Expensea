"""Opaque keyset cursors for stable ledger timelines."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.ledger.errors import InvalidCursorError, LedgerValidationError

CURSOR_VERSION = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class TransactionCursor:
    """The stable sort keys encoded by a transaction cursor."""

    occurred_at: datetime
    transaction_id: UUID


def validate_page_size(first: int) -> int:
    """Return a bounded forward page size."""
    if first < 1 or first > MAX_PAGE_SIZE:
        raise LedgerValidationError(
            code="INVALID_PAGE_SIZE",
            message=f"first must be between 1 and {MAX_PAGE_SIZE}.",
            field="first",
        )
    return first


def encode_transaction_cursor(cursor: TransactionCursor) -> str:
    """Encode UTC timestamp and UUID sort keys without exposing an API contract."""
    occurred_at = cursor.occurred_at
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        msg = "Cursor timestamps must be timezone-aware"
        raise ValueError(msg)

    payload = {
        "at": occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "id": str(cursor.transaction_id),
        "v": CURSOR_VERSION,
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(serialized).decode("ascii").rstrip("=")


def decode_transaction_cursor(raw_cursor: str) -> TransactionCursor:
    """Decode and strictly validate one opaque transaction cursor."""
    try:
        padded = raw_cursor + ("=" * (-len(raw_cursor) % 4))
        serialized = base64.b64decode(
            padded,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(serialized)
        if not isinstance(payload, dict) or set(payload) != {"at", "id", "v"}:
            raise InvalidCursorError
        if payload["v"] != CURSOR_VERSION:
            raise InvalidCursorError
        if not isinstance(payload["at"], str) or not isinstance(payload["id"], str):
            raise InvalidCursorError

        occurred_at = datetime.fromisoformat(payload["at"].replace("Z", "+00:00"))
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise InvalidCursorError
        transaction_id = UUID(payload["id"])
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        raise InvalidCursorError from None

    return TransactionCursor(
        occurred_at=occurred_at.astimezone(UTC),
        transaction_id=transaction_id,
    )
