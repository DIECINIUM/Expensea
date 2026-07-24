"""Add replay-safe ingestion and provenance records.

Revision ID: 20260724_0003
Revises: 20260724_0002
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create source, raw-event, normalized-event, and evidence persistence."""
    op.drop_constraint(
        op.f("ck_transactions_transaction_source"),
        "transactions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_transactions_transaction_source"),
        "transactions",
        "source IN ('manual', 'ingestion')",
    )

    op.create_table(
        "source_connections",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "connector_type",
            sa.Enum(
                "manual_note",
                "csv_import",
                "mock_receipt",
                "gmail",
                "google_keep_takeout",
                name="connector_type",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("connection_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "paused",
                "error",
                "disconnected",
                name="source_connection_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cursor",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(connection_key)) > 0",
            name=op.f("ck_source_connections_connection_key_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name=op.f("ck_source_connections_display_name_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_source_connections_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_connections")),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_source_connections_id_user",
        ),
        sa.UniqueConstraint(
            "user_id",
            "connector_type",
            "connection_key",
            name="uq_source_connections_user_connector_key",
        ),
    )
    op.create_index(
        "ix_source_connections_user_status",
        "source_connections",
        ["user_id", "status"],
        unique=False,
    )

    op.create_table(
        "raw_events",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_connection_id", sa.Uuid(), nullable=False),
        sa.Column("identity_key", sa.String(length=320), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_event_type", sa.String(length=80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_raw_events_content_sha256_format"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(identity_key)) > 0",
            name=op.f("ck_raw_events_identity_key_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(source_event_type)) > 0",
            name=op.f("ck_raw_events_source_event_type_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["source_connection_id", "user_id"],
            ["source_connections.id", "source_connections.user_id"],
            name="fk_raw_events_connection_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_events")),
        sa.UniqueConstraint(
            "source_connection_id",
            "identity_key",
            name="uq_raw_events_connection_identity",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_raw_events_id_user"),
    )
    op.create_index(
        "ix_raw_events_connection_content_hash",
        "raw_events",
        ["source_connection_id", "content_sha256"],
        unique=False,
    )
    op.create_index(
        "ix_raw_events_connection_created",
        "raw_events",
        ["source_connection_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_raw_events_user_created",
        "raw_events",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "raw_event_processing",
        sa.Column("raw_event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "received",
                "normalized",
                "processed",
                "needs_review",
                "failed",
                name="raw_event_state",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default=sa.text("'received'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_raw_event_processing_attempt_count_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_raw_event_processing_event_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "raw_event_id",
            name=op.f("pk_raw_event_processing"),
        ),
    )
    op.create_index(
        "ix_raw_event_processing_user_state",
        "raw_event_processing",
        ["user_id", "state", "updated_at"],
        unique=False,
    )

    op.create_table(
        "normalized_financial_events",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("raw_event_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("normalizer_key", sa.String(length=80), nullable=False),
        sa.Column("normalizer_version", sa.String(length=40), nullable=False),
        sa.Column(
            "event_kind",
            sa.Enum(
                "expense",
                "income",
                "transfer",
                "refund",
                "shared_expense",
                "receivable",
                "payable",
                "recurring",
                "unknown",
                name="normalized_event_kind",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merchant_name", sa.String(length=160), nullable=True),
        sa.Column("counterparty", sa.String(length=160), nullable=True),
        sa.Column("category_hint", sa.String(length=80), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Numeric(precision=5, scale=4),
            nullable=True,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0",
            name=op.f("ck_normalized_financial_events_amount_positive_when_present"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_normalized_financial_events_confidence_range"),
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_normalized_financial_events_currency_format_when_present"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(description)) > 0",
            name=op.f("ck_normalized_financial_events_description_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalizer_key)) > 0",
            name=op.f("ck_normalized_financial_events_normalizer_key_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalizer_version)) > 0",
            name=op.f("ck_normalized_financial_events_normalizer_version_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(schema_version)) > 0",
            name=op.f("ck_normalized_financial_events_schema_version_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_normalized_events_raw_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_normalized_financial_events"),
        ),
        sa.UniqueConstraint(
            "id",
            "raw_event_id",
            "user_id",
            name="uq_normalized_events_id_raw_user",
        ),
        sa.UniqueConstraint(
            "raw_event_id",
            "schema_version",
            "normalizer_key",
            "normalizer_version",
            name="uq_normalized_events_raw_contract",
        ),
    )
    op.create_index(
        "ix_normalized_events_user_kind_occurred",
        "normalized_financial_events",
        ["user_id", "event_kind", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "evidence",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("raw_event_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_event_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column(
            "evidence_kind",
            sa.Enum(
                "source_event",
                name="evidence_kind",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default=sa.text("'source_event'"),
            nullable=False,
        ),
        sa.Column(
            "locator",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("excerpt", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "excerpt IS NULL OR char_length(excerpt) <= 500",
            name=op.f("ck_evidence_excerpt_bounded"),
        ),
        sa.ForeignKeyConstraint(
            ["normalized_event_id", "raw_event_id", "user_id"],
            [
                "normalized_financial_events.id",
                "normalized_financial_events.raw_event_id",
                "normalized_financial_events.user_id",
            ],
            name="fk_evidence_normalized_raw_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_evidence_raw_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_evidence_transaction_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        sa.UniqueConstraint(
            "normalized_event_id",
            name="uq_evidence_normalized_event",
        ),
    )
    op.create_index(
        "ix_evidence_user_raw_event",
        "evidence",
        ["user_id", "raw_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_user_transaction",
        "evidence",
        ["user_id", "transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove ingestion records and restore the manual-only source vocabulary."""
    op.drop_index("ix_evidence_user_transaction", table_name="evidence")
    op.drop_index("ix_evidence_user_raw_event", table_name="evidence")
    op.drop_table("evidence")

    op.drop_index(
        "ix_normalized_events_user_kind_occurred",
        table_name="normalized_financial_events",
    )
    op.drop_table("normalized_financial_events")

    op.drop_index(
        "ix_raw_event_processing_user_state",
        table_name="raw_event_processing",
    )
    op.drop_table("raw_event_processing")

    op.drop_index(
        "ix_raw_events_user_created",
        table_name="raw_events",
    )
    op.drop_index(
        "ix_raw_events_connection_created",
        table_name="raw_events",
    )
    op.drop_index(
        "ix_raw_events_connection_content_hash",
        table_name="raw_events",
    )
    op.drop_table("raw_events")

    op.drop_index(
        "ix_source_connections_user_status",
        table_name="source_connections",
    )
    op.drop_table("source_connections")

    op.drop_constraint(
        op.f("ck_transactions_transaction_source"),
        "transactions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_transactions_transaction_source"),
        "transactions",
        "source = 'manual'",
    )
