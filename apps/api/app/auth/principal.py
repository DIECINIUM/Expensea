"""Trusted application identity."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated identity injected into application boundaries."""

    user_id: UUID
