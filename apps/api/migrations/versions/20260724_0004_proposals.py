"""Add review-first structured extraction proposals.

Revision ID: 20260724_0004
Revises: 20260724_0003
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0004"
down_revision: str | None = "20260724_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create owner-scoped proposal review and canonical-target provenance."""
    op.create_table(
        "financial_event_proposals",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("raw_event_id", sa.Uuid(), nullable=False),
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
                name="proposal_event_kind",
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
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("merchant_name", sa.String(length=160), nullable=True),
        sa.Column("counterparty", sa.String(length=160), nullable=True),
        sa.Column(
            "recurrence_rule",
            sa.Enum(
                "weekly",
                "monthly",
                "quarterly",
                "yearly",
                name="proposal_recurrence_rule",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=True,
        ),
        sa.Column("next_expected_date", sa.Date(), nullable=True),
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
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "needs_review",
                "approved",
                "rejected",
                name="proposal_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default=sa.text("'needs_review'"),
            nullable=False,
        ),
        sa.Column(
            "review_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_name", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("receivable_id", sa.Uuid(), nullable=True),
        sa.Column("payable_id", sa.Uuid(), nullable=True),
        sa.Column("recurring_payment_id", sa.Uuid(), nullable=True),
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
            "amount IS NULL OR amount > 0",
            name=op.f("ck_financial_event_proposals_amount_positive_when_present"),
        ),
        sa.CheckConstraint(
            "(amount IS NULL) = (currency IS NULL)",
            name=op.f("ck_financial_event_proposals_money_pair_complete"),
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_financial_event_proposals_currency_format_when_present"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(description)) > 0",
            name=op.f("ck_financial_event_proposals_description_not_blank"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_financial_event_proposals_confidence_range"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(tags) = 'array'",
            name=op.f("ck_financial_event_proposals_tags_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(review_reasons) = 'array'",
            name=op.f("ck_financial_event_proposals_review_reasons_array"),
        ),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name=op.f("ck_financial_event_proposals_latency_non_negative"),
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name=op.f("ck_financial_event_proposals_input_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name=op.f("ck_financial_event_proposals_output_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(transaction_id, receivable_id, payable_id, recurring_payment_id) <= 1",
            name=op.f("ck_financial_event_proposals_at_most_one_canonical_target"),
        ),
        sa.CheckConstraint(
            "(status = 'approved' AND "
            "num_nonnulls(transaction_id, receivable_id, payable_id, "
            "recurring_payment_id) = 1) OR "
            "(status <> 'approved' AND "
            "num_nonnulls(transaction_id, receivable_id, payable_id, "
            "recurring_payment_id) = 0)",
            name=op.f("ck_financial_event_proposals_approved_has_canonical_target"),
        ),
        sa.ForeignKeyConstraint(
            ["payable_id", "user_id", "currency"],
            ["payables.id", "payables.user_id", "payables.currency"],
            name="fk_financial_event_proposals_payable_owner_currency",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_financial_event_proposals_raw_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receivable_id", "user_id", "currency"],
            ["receivables.id", "receivables.user_id", "receivables.currency"],
            name="fk_financial_event_proposals_receivable_owner_currency",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recurring_payment_id", "user_id"],
            ["recurring_payments.id", "recurring_payments.user_id"],
            name="fk_financial_event_proposals_recurring_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_financial_event_proposals_transaction_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_financial_event_proposals"),
        ),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_financial_event_proposals_id_user",
        ),
        sa.UniqueConstraint(
            "raw_event_id",
            "prompt_name",
            "prompt_version",
            "schema_version",
            name="uq_financial_event_proposals_raw_prompt",
        ),
    )
    op.create_index(
        "ix_financial_event_proposals_user_raw",
        "financial_event_proposals",
        ["user_id", "raw_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_event_proposals_user_status_created",
        "financial_event_proposals",
        ["user_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove extracted proposals without modifying canonical ledger records."""
    op.drop_index(
        "ix_financial_event_proposals_user_status_created",
        table_name="financial_event_proposals",
    )
    op.drop_index(
        "ix_financial_event_proposals_user_raw",
        table_name="financial_event_proposals",
    )
    op.drop_table("financial_event_proposals")
