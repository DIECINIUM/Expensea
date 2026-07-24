"""Stable AI boundary failures that never include private prompt content."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AIError(Exception):
    """Base content-safe AI error."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class AIProviderError(AIError):
    """The configured provider was unavailable or returned an invalid envelope."""


class AIOutputError(AIError):
    """Provider content failed the requested financial schema."""
