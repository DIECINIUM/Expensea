"""Add personalized categorization and correction memory.

Revision ID: 20260727_0007
Revises: 20260724_0006
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0007"
down_revision: str | None = "20260724_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("category_source", sa.String(length=24)))
    op.add_column("transactions", sa.Column("category_classifier_version", sa.String(length=40)))
    op.add_column("transactions", sa.Column("category_confidence", sa.Numeric(5, 4)))
    op.add_column(
        "transactions",
        sa.Column(
            "category_overridden", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_transactions_category_source"),
        "transactions",
        "category_source IS NULL OR category_source IN "
        "('user_rule','merchant_map','verified_correction','retrieval','model','user_override')",
    )
    op.create_check_constraint(
        op.f("ck_transactions_category_confidence_range"),
        "transactions",
        "category_confidence IS NULL OR (category_confidence >= 0 AND category_confidence <= 1)",
    )
    # Existing explicit categories predate assignment metadata.
    op.execute(
        "UPDATE transactions SET category_source='user_override', "
        "category_classifier_version='legacy-explicit-v1', category_confidence=1.0000, "
        "category_overridden=true WHERE category_id IS NOT NULL"
    )
    op.create_check_constraint(
        op.f("ck_transactions_category_metadata_consistent"),
        "transactions",
        "(category_id IS NULL AND category_source IS NULL AND category_classifier_version IS NULL "
        "AND category_confidence IS NULL AND category_overridden = false) OR "
        "(category_id IS NOT NULL AND category_source IS NOT NULL "
        "AND category_classifier_version IS NOT NULL AND category_confidence IS NOT NULL)",
    )

    op.create_table(
        "category_rules",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_pattern", sa.String(length=120), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "char_length(btrim(normalized_pattern)) > 0",
            name=op.f("ck_category_rules_pattern_not_blank"),
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_category_rules")),
        sa.UniqueConstraint("user_id", "normalized_pattern", name="uq_category_rules_user_pattern"),
    )
    op.create_index(
        "ix_category_rules_user_enabled_priority",
        "category_rules",
        ["user_id", "enabled", "priority"],
    )

    op.create_table(
        "merchant_category_maps",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_category_maps")),
        sa.UniqueConstraint(
            "user_id", "merchant_id", name="uq_merchant_category_maps_user_merchant"
        ),
    )
    op.create_index(
        "ix_merchant_category_maps_user_merchant",
        "merchant_category_maps",
        ["user_id", "merchant_id"],
    )

    op.create_table(
        "user_corrections",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("previous_category_id", sa.Uuid()),
        sa.Column("corrected_category_id", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid()),
        sa.Column("normalized_description", sa.String(length=500), nullable=False),
        sa.Column("classifier_version", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalized_description)) > 0",
            name=op.f("ck_user_corrections_description_not_blank"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name=op.f("ck_user_corrections_confidence_range")
        ),
        sa.ForeignKeyConstraint(["corrected_category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_user_corrections_transaction_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_corrections")),
    )
    op.create_index(
        "ix_user_corrections_user_description_created",
        "user_corrections",
        ["user_id", "normalized_description", "created_at"],
    )
    op.create_index(
        "ix_user_corrections_user_transaction_created",
        "user_corrections",
        ["user_id", "transaction_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("user_corrections")
    op.drop_table("merchant_category_maps")
    op.drop_table("category_rules")
    op.drop_constraint(
        op.f("ck_transactions_category_metadata_consistent"), "transactions", type_="check"
    )
    op.drop_constraint(
        op.f("ck_transactions_category_confidence_range"), "transactions", type_="check"
    )
    op.drop_constraint(op.f("ck_transactions_category_source"), "transactions", type_="check")
    op.drop_column("transactions", "category_overridden")
    op.drop_column("transactions", "category_confidence")
    op.drop_column("transactions", "category_classifier_version")
    op.drop_column("transactions", "category_source")
