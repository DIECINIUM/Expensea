"""Stable normalization for user-entered lookup values."""

import unicodedata


def normalize_display_text(value: str) -> str:
    """Normalize Unicode and collapse surrounding/repeated whitespace."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize_lookup_text(value: str) -> str:
    """Create a case-insensitive lookup key from display text."""
    return normalize_display_text(value).casefold()


def normalize_email(value: str) -> str:
    """Normalize the application login identifier."""
    return unicodedata.normalize("NFKC", value).strip().casefold()
