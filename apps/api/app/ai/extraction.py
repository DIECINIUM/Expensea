"""Structured financial-note extraction with deterministic review policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.ai.contracts import (
    ProviderTelemetry,
    StructuredCompletionProvider,
    StructuredCompletionRequest,
)
from app.ai.errors import AIOutputError
from app.ai.prompts.financial_note_v1 import (
    PROMPT_NAME,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    SYSTEM_PROMPT,
)
from app.domain.enums import NormalizedEventKind, RecurrenceRule
from app.domain.normalization import normalize_display_text
from app.ingestion.contracts import MAX_TAG_LENGTH, MAX_TAGS
from app.ledger.commands import parse_currency
from app.ledger.errors import LedgerValidationError
from app.ledger.periods import parse_timezone

_KINDS_REQUIRING_MONEY = frozenset(
    {
        NormalizedEventKind.EXPENSE,
        NormalizedEventKind.INCOME,
        NormalizedEventKind.REFUND,
        NormalizedEventKind.SHARED_EXPENSE,
        NormalizedEventKind.RECEIVABLE,
        NormalizedEventKind.PAYABLE,
        NormalizedEventKind.RECURRING,
    }
)


class ExtractedFinancialEvent(BaseModel):
    """Untrusted model output after strict structural validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_kind: NormalizedEventKind
    amount: Decimal | None = Field(default=None, gt=0, max_digits=19, decimal_places=4)
    currency: str | None = None
    description: str = Field(min_length=1, max_length=500)
    occurred_at: datetime | None = None
    due_date: date | None = None
    merchant_name: str | None = Field(default=None, max_length=160)
    counterparty: str | None = Field(default=None, max_length=160)
    recurrence_rule: RecurrenceRule | None = None
    category_hint: str | None = Field(default=None, max_length=80)
    tags: tuple[str, ...] = ()
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)

    @field_validator(
        "description",
        "merchant_name",
        "counterparty",
        "category_hint",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
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
        tags: list[str] = []
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
                tags.append(tag)
        if len(tags) > MAX_TAGS:
            raise ValueError(f"events cannot have more than {MAX_TAGS} tags")
        return tuple(tags)

    @model_validator(mode="after")
    def validate_money_pair(self) -> Self:
        if (self.amount is None) != (self.currency is None):
            raise ValueError("amount and currency must either both be present or both be unknown")
        return self


@dataclass(frozen=True, slots=True)
class NoteExtractionContext:
    """Trusted calendar and currency context supplied outside source text."""

    source_timestamp: datetime
    timezone: str
    default_currency: str


@dataclass(frozen=True, slots=True)
class FinancialExtractionResult:
    """Schema-valid proposal plus deterministic review reasons and telemetry."""

    event: ExtractedFinancialEvent
    requires_review: bool
    review_reasons: tuple[str, ...]
    prompt_name: str
    prompt_version: str
    schema_version: str
    telemetry: ProviderTelemetry


class FinancialNoteExtractor:
    """Interpret one note while keeping approval policy deterministic."""

    def __init__(
        self,
        provider: StructuredCompletionProvider,
        *,
        max_input_chars: int,
        review_confidence_threshold: Decimal,
    ) -> None:
        self._provider = provider
        self._max_input_chars = max_input_chars
        self._review_threshold = review_confidence_threshold

    async def extract(
        self,
        note: str,
        context: NoteExtractionContext,
    ) -> FinancialExtractionResult:
        normalized_note = note.strip()
        if not normalized_note:
            raise AIOutputError(
                code="EMPTY_FINANCIAL_NOTE",
                message="The financial note cannot be blank.",
            )
        if len(normalized_note) > self._max_input_chars:
            raise AIOutputError(
                code="FINANCIAL_NOTE_TOO_LONG",
                message="The financial note exceeds the configured extraction limit.",
            )
        if context.source_timestamp.tzinfo is None or context.source_timestamp.utcoffset() is None:
            raise AIOutputError(
                code="INVALID_SOURCE_TIMESTAMP",
                message="The note source timestamp must include a timezone offset.",
            )
        try:
            parse_timezone(context.timezone)
        except LedgerValidationError as exc:
            raise AIOutputError(
                code="INVALID_SOURCE_TIMEZONE",
                message="The note context timezone is not recognized.",
            ) from exc
        try:
            default_currency = parse_currency(context.default_currency)
        except LedgerValidationError as exc:
            raise AIOutputError(
                code="INVALID_DEFAULT_CURRENCY",
                message="The note context currency is not supported.",
            ) from exc

        request = StructuredCompletionRequest(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(
                normalized_note,
                source_timestamp=context.source_timestamp,
                timezone=context.timezone,
                default_currency=default_currency,
            ),
            response_schema=ExtractedFinancialEvent.model_json_schema(),
            prompt_name=PROMPT_NAME,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        )
        completion = await self._provider.complete(request)
        try:
            event = ExtractedFinancialEvent.model_validate(completion.data)
        except ValidationError as exc:
            raise AIOutputError(
                code="AI_OUTPUT_SCHEMA_INVALID",
                message="The model output did not satisfy the financial event schema.",
            ) from exc

        reasons = _review_reasons(
            event,
            threshold=self._review_threshold,
        )
        return FinancialExtractionResult(
            event=event,
            requires_review=True,
            review_reasons=reasons,
            prompt_name=PROMPT_NAME,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            telemetry=completion.telemetry,
        )


def _build_user_prompt(
    note: str,
    *,
    source_timestamp: datetime,
    timezone: str,
    default_currency: str,
) -> str:
    return (
        "TRUSTED_CONTEXT\n"
        f"source_timestamp={source_timestamp.isoformat()}\n"
        f"timezone={timezone}\n"
        f"default_currency={default_currency}\n"
        "END_TRUSTED_CONTEXT\n\n"
        "UNTRUSTED_NOTE\n"
        f"{note}\n"
        "END_UNTRUSTED_NOTE"
    )


def _review_reasons(
    event: ExtractedFinancialEvent,
    *,
    threshold: Decimal,
) -> tuple[str, ...]:
    reasons = ["AI_REVIEW_REQUIRED"]
    if event.confidence < threshold:
        reasons.append("LOW_CONFIDENCE")
    if event.event_kind in _KINDS_REQUIRING_MONEY and event.amount is None:
        reasons.append("MISSING_AMOUNT_OR_CURRENCY")
    if event.occurred_at is None:
        reasons.append("MISSING_OCCURRED_AT")
    if (
        event.event_kind in {NormalizedEventKind.RECEIVABLE, NormalizedEventKind.PAYABLE}
        and event.counterparty is None
    ):
        reasons.append("MISSING_COUNTERPARTY")
    if event.event_kind is NormalizedEventKind.RECURRING and event.recurrence_rule is None:
        reasons.append("MISSING_RECURRENCE_RULE")
    return tuple(reasons)
