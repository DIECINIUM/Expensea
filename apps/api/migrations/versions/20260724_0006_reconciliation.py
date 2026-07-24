"""Add deterministic reconciliation cases and audit actions.

Revision ID: 20260724_0006
Revises: 20260724_0005
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0006"
down_revision: str | None = "20260724_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create owner-scoped duplicate decisions, review state, and audit history."""
    op.add_column(
        "normalized_financial_events",
        sa.Column(
            "payment_identifiers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_normalized_financial_events_payment_identifiers_array"),
        "normalized_financial_events",
        "jsonb_typeof(payment_identifiers) = 'array'",
    )
    op.create_index(
        "ix_normalized_events_payment_identifiers",
        "normalized_financial_events",
        ["payment_identifiers"],
        unique=False,
        postgresql_using="gin",
    )

    op.drop_constraint(
        op.f("ck_financial_event_proposals_proposal_status"),
        "financial_event_proposals",
        type_="check",
    )
    op.alter_column(
        "financial_event_proposals",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=24),
        existing_nullable=False,
        existing_server_default=sa.text("'needs_review'"),
    )
    op.create_check_constraint(
        op.f("ck_financial_event_proposals_proposal_status"),
        "financial_event_proposals",
        "status IN ('needs_review', 'reconciliation_review', 'approved', 'rejected')",
    )

    op.create_table(
        "reconciliation_cases",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_event_id", sa.Uuid(), nullable=False),
        sa.Column("raw_event_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("resulting_transaction_id", sa.Uuid(), nullable=True),
        sa.Column(
            "initial_decision",
            sa.Enum(
                "merge",
                "possible_duplicate",
                "new_transaction",
                name="reconciliation_decision",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "merged",
                "kept_separate",
                "unmerged",
                name="reconciliation_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("score_version", sa.String(length=40), nullable=False),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence_locator",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("evidence_excerpt", sa.String(length=500), nullable=True),
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
            "(initial_decision = 'merge' AND status IN ('merged', 'unmerged')) OR "
            "(initial_decision = 'possible_duplicate') OR "
            "(initial_decision = 'new_transaction' AND status = 'kept_separate')",
            name=op.f("ck_reconciliation_cases_initial_decision_lifecycle"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_locator) = 'object'",
            name=op.f("ck_reconciliation_cases_evidence_locator_object"),
        ),
        sa.CheckConstraint(
            "evidence_excerpt IS NULL OR char_length(evidence_excerpt) <= 500",
            name=op.f("ck_reconciliation_cases_evidence_excerpt_bounded"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reasons) = 'array'",
            name=op.f("ck_reconciliation_cases_reasons_array"),
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1",
            name=op.f("ck_reconciliation_cases_score_range"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(score_version)) > 0",
            name=op.f("ck_reconciliation_cases_score_version_not_blank"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND initial_decision = 'possible_duplicate' "
            "AND candidate_transaction_id IS NOT NULL "
            "AND resulting_transaction_id IS NULL) OR "
            "(status = 'merged' AND candidate_transaction_id IS NOT NULL "
            "AND resulting_transaction_id = candidate_transaction_id) OR "
            "(status = 'kept_separate' AND resulting_transaction_id IS NOT NULL "
            "AND resulting_transaction_id IS DISTINCT FROM candidate_transaction_id) OR "
            "(status = 'unmerged' AND candidate_transaction_id IS NOT NULL "
            "AND resulting_transaction_id IS NOT NULL "
            "AND resulting_transaction_id <> candidate_transaction_id)",
            name=op.f("ck_reconciliation_cases_status_targets_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_cases_candidate_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["normalized_event_id", "raw_event_id", "user_id"],
            [
                "normalized_financial_events.id",
                "normalized_financial_events.raw_event_id",
                "normalized_financial_events.user_id",
            ],
            name="fk_reconciliation_cases_normalized_raw_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resulting_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_cases_resulting_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reconciliation_cases_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_cases")),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_reconciliation_cases_id_user",
        ),
        sa.UniqueConstraint(
            "normalized_event_id",
            name="uq_reconciliation_cases_normalized_event",
        ),
    )
    op.create_index(
        "ix_reconciliation_cases_user_candidate",
        "reconciliation_cases",
        ["user_id", "candidate_transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_cases_user_status_created",
        "reconciliation_cases",
        ["user_id", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "reconciliation_actions",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum(
                "candidate_flagged",
                "auto_merged",
                "created_new",
                "user_merged",
                "user_kept_separate",
                "user_unmerged",
                name="reconciliation_action_type",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("from_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("to_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
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
            "jsonb_typeof(reasons) = 'array'",
            name=op.f("ck_reconciliation_actions_reasons_array"),
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1",
            name=op.f("ck_reconciliation_actions_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "user_id"],
            ["reconciliation_cases.id", "reconciliation_cases.user_id"],
            name="fk_reconciliation_actions_case_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["from_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_actions_from_transaction_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_actions_to_transaction_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_actions")),
    )
    op.create_index(
        "ix_reconciliation_actions_case_created",
        "reconciliation_actions",
        ["case_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_actions_user_created",
        "reconciliation_actions",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove reconciliation state and restore unresolved proposals to review."""
    op.drop_index(
        "ix_reconciliation_actions_user_created",
        table_name="reconciliation_actions",
    )
    op.drop_index(
        "ix_reconciliation_actions_case_created",
        table_name="reconciliation_actions",
    )
    op.drop_table("reconciliation_actions")

    op.drop_index(
        "ix_reconciliation_cases_user_status_created",
        table_name="reconciliation_cases",
    )
    op.drop_index(
        "ix_reconciliation_cases_user_candidate",
        table_name="reconciliation_cases",
    )
    op.drop_table("reconciliation_cases")

    op.execute(
        "UPDATE financial_event_proposals "
        "SET status = 'needs_review' "
        "WHERE status = 'reconciliation_review'"
    )
    op.drop_constraint(
        op.f("ck_financial_event_proposals_proposal_status"),
        "financial_event_proposals",
        type_="check",
    )
    op.alter_column(
        "financial_event_proposals",
        "status",
        existing_type=sa.String(length=24),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'needs_review'"),
    )
    op.create_check_constraint(
        op.f("ck_financial_event_proposals_proposal_status"),
        "financial_event_proposals",
        "status IN ('needs_review', 'approved', 'rejected')",
    )

    op.drop_index(
        "ix_normalized_events_payment_identifiers",
        table_name="normalized_financial_events",
        postgresql_using="gin",
    )
    op.drop_constraint(
        op.f("ck_normalized_financial_events_payment_identifiers_array"),
        "normalized_financial_events",
        type_="check",
    )
    op.drop_column("normalized_financial_events", "payment_identifiers")
