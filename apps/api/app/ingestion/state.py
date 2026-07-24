"""Deterministic raw-event processing state transitions."""

from app.domain.enums import RawEventState
from app.ingestion.errors import IngestionConflictError

_ALLOWED_TRANSITIONS: dict[RawEventState, frozenset[RawEventState]] = {
    RawEventState.RECEIVED: frozenset(
        {
            RawEventState.NORMALIZED,
            RawEventState.FAILED,
        }
    ),
    RawEventState.NORMALIZED: frozenset(
        {
            RawEventState.PROCESSED,
            RawEventState.NEEDS_REVIEW,
            RawEventState.FAILED,
        }
    ),
    RawEventState.FAILED: frozenset(
        {
            RawEventState.NORMALIZED,
            RawEventState.FAILED,
        }
    ),
    RawEventState.NEEDS_REVIEW: frozenset({RawEventState.PROCESSED}),
    RawEventState.PROCESSED: frozenset(),
}


def require_state_transition(
    current: RawEventState,
    target: RawEventState,
) -> None:
    """Reject undeclared transitions before persistence."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise IngestionConflictError(
            code="INVALID_INGESTION_STATE_TRANSITION",
            message=f"Raw event cannot transition from {current.value} to {target.value}.",
        )
