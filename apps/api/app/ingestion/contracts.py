"""Versioned provider-neutral financial-event contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import NormalizedEventKind
from app.domain.normalization import normalize_display_text
from app.ledger.commands import parse_currency
from app.ledger.errors import LedgerValidationError

NORMALIZED_EVENT_SCHEMA_VERSION: Literal["financial-event/v1"] = "financial-event/v1"
MAX_TAGS = 12
MAX_TAG_LENGTH = 40


class NormalizedFinancialEventV1(BaseModel):
    """Validated event emitted by every Phase 2 connector normalizer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["financial-event/v1"] = NORMALIZED_EVENT_SCHEMA_VERSION
    event_kind: NormalizedEventKind
    amount: Decimal | None = Field(default=None, gt=0, max_digits=19, decimal_places=4)
    currency: str | None = None
    description: str = Field(min_length=1, max_length=500)
    occurred_at: datetime | None = None
    merchant_name: str | None = Field(default=None, max_length=160)
    counterparty: str | None = Field(default=None, max_length=160)
    category_hint: str | None = Field(default=None, max_length=80)
    tags: tuple[str, ...] = ()
    confidence: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )

    @field_validator(
        "description",
        "merchant_name",
        "counterparty",
        "category_hint",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        """Normalize textual source fields without inventing missing values."""
        if not isinstance(value, str):
            return value
        normalized = normalize_display_text(value)
        return normalized or None

    @field_validator("description")
    @classmethod
    def require_description(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("description cannot be blank")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return parse_currency(value)
        except LedgerValidationError as exc:
            raise ValueError("currency is not supported") from exc

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value.astimezone(UTC)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("tags must be strings")
            tag = normalize_display_text(item)
            if not tag:
                continue
            if len(tag) > MAX_TAG_LENGTH:
                raise ValueError(f"tags cannot exceed {MAX_TAG_LENGTH} characters")
            lookup = tag.casefold()
            if lookup not in seen:
                seen.add(lookup)
                normalized.append(tag)
        if len(normalized) > MAX_TAGS:
            raise ValueError(f"events cannot have more than {MAX_TAGS} tags")
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_amount_currency_pair(self) -> Self:
        """Never allow a monetary value without its unit, or vice versa."""
        if (self.amount is None) != (self.currency is None):
            raise ValueError("amount and currency must either both be present or both be unknown")
        return self
