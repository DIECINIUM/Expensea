"""Durable owner-scoped asynchronous extraction.

Revision ID: 20261011_0009
Revises: 20261011_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261011_0009"
down_revision: str | None = "20261011_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("review_retries", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(40)),
        sa.Column("result", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_jobs_owner_idempotency"),
        sa.CheckConstraint("kind IN ('financial_note_extract')", name="kind_allowed"),
        sa.CheckConstraint(
            "status IN ('queued','running','retry_wait','succeeded','dead_letter','cancelled')",
            name="status_allowed",
        ),
        sa.CheckConstraint("attempts >= 0 AND attempts <= max_attempts", name="attempts_bounded"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 5", name="max_attempts_bounded"),
        sa.CheckConstraint("review_retries BETWEEN 0 AND 3", name="review_retries_bounded"),
        sa.CheckConstraint(
            "(status = 'running' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'running' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="lease_consistent",
        ),
        sa.CheckConstraint(
            "octet_length(payload::text) <= 32768 AND jsonb_typeof(payload) = 'object'",
            name="payload_bounded",
        ),
    )
    op.create_index("ix_jobs_ready", "jobs", ["status", "available_at", "created_at"])
    op.create_index("ix_jobs_owner_created", "jobs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_owner_created", table_name="jobs")
    op.drop_index("ix_jobs_ready", table_name="jobs")
    op.drop_table("jobs")
