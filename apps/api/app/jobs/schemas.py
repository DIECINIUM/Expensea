"""Only financial-note extraction may cross this job boundary."""

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_REQUEST_BYTES = 32_768


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class FinancialNotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=8000)
    source_timestamp: AwareDatetime
    labels: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("note")
    @classmethod
    def nonblank_note(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("note must not be blank")
        return value

    @field_validator("labels")
    @classmethod
    def bounded_labels(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 40 or "\x00" in value for value in values):
            raise ValueError("labels must be nonblank and at most 40 characters")
        return values

    @model_validator(mode="after")
    def bounded_storage(self) -> "FinancialNotePayload":
        encoded = json.dumps(self.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > 30_000:
            raise ValueError("financial-note payload exceeds the durable byte limit")
        return self


class EnqueueJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["financial_note_extract"]
    idempotency_key: UUID
    payload: FinancialNotePayload

    def fingerprint(self) -> str:
        return hashlib.sha256(
            (self.kind + ":" + self.payload.model_dump_json()).encode("utf-8")
        ).hexdigest()


class JobResult(BaseModel):
    proposal_id: UUID


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: JobStatus
    attempts: int
    max_attempts: int
    review_retries: int
    created_at: datetime
    updated_at: datetime
    available_at: datetime
    completed_at: datetime | None
    error_code: str | None
    result: JobResult | None


class QueueSnapshot(BaseModel):
    """Owner-only status counts; fixed fields, no raw notes or global owner information."""

    queued: int = 0
    running: int = 0
    retry_wait: int = 0
    succeeded: int = 0
    dead_letter: int = 0
    cancelled: int = 0
    pending_limit: int
    max_attempts: int


class JobError(Exception):
    """A fixed public error code; never include exception or note text."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
