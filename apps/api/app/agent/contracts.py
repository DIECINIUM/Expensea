from datetime import date
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolName(StrEnum):
    SUMMARY = "get_financial_summary"
    TRANSACTIONS = "get_transactions"
    COMPARE = "compare_periods"
    RECEIVABLES = "get_outstanding_receivables"
    RELATIONSHIP = "get_person_financial_relationship"
    RECURRING = "get_upcoming_recurring"
    TRANSACTION = "get_transaction_detail"
    UNSUPPORTED = "unsupported"


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1, max_length=1000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    person_id: UUID | None = None
    transaction_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question cannot be blank")
        return value


class IntentChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: ToolName


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(max_length=160)
    value: str = Field(max_length=100, pattern=r"^-?\d+(\.\d+)?$")
    currency: str | None = None
    record_id: UUID | None = None
    record_kind: str | None = None


class QuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["answered", "unsupported", "needs_input", "busy", "resource_limit"]
    mode: Literal[
        "deterministic",
        "deterministic_provider_unavailable",
        "structured_intent_deterministic_answer",
    ]
    tool: ToolName
    answer: str = Field(max_length=12000)
    facts: tuple[Fact, ...] = Field(default=(), max_length=30)
    period_start: date | None = None
    period_end: date | None = None
    period_end_inclusive: bool = False
    previous_period_start: date | None = None
    previous_period_end: date | None = None
    truncated: bool = False
    limitations: tuple[str, ...] = ()
