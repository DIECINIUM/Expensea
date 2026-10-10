"""Durable owner-scoped jobs; payloads remain private to the worker."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_jobs_owner_idempotency"),
        CheckConstraint("kind IN ('financial_note_extract')", name="kind_allowed"),
        CheckConstraint(
            "status IN ('queued','running','retry_wait','succeeded','dead_letter','cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("attempts >= 0 AND attempts <= max_attempts", name="attempts_bounded"),
        CheckConstraint("max_attempts BETWEEN 1 AND 5", name="max_attempts_bounded"),
        CheckConstraint("review_retries BETWEEN 0 AND 3", name="review_retries_bounded"),
        CheckConstraint(
            "(status = 'running' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'running' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="lease_consistent",
        ),
        CheckConstraint(
            "octet_length(payload::text) <= 32768 AND jsonb_typeof(payload) = 'object'",
            name="payload_bounded",
        ),
        Index("ix_jobs_ready", "status", "available_at", "created_at"),
        Index("ix_jobs_owner_created", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    review_retries: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
