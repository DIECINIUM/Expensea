"""Create the deterministic Phase 1 financial ledger.

Revision ID: 20260724_0002
Revises: 20260723_0001
Create Date: 2026-07-24
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0002"
down_revision: str | None = "20260723_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_CATEGORIES = (
    {
        "id": UUID("00000000-0000-4000-8000-000000000001"),
        "name": "Food",
        "normalized_name": "food",
        "parent_category_id": None,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000002"),
        "name": "Food Delivery",
        "normalized_name": "food delivery",
        "parent_category_id": UUID("00000000-0000-4000-8000-000000000001"),
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000003"),
        "name": "Restaurant",
        "normalized_name": "restaurant",
        "parent_category_id": UUID("00000000-0000-4000-8000-000000000001"),
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000004"),
        "name": "Grocery",
        "normalized_name": "grocery",
        "parent_category_id": UUID("00000000-0000-4000-8000-000000000001"),
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000005"),
        "name": "Travel",
        "normalized_name": "travel",
        "parent_category_id": None,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000006"),
        "name": "Shopping",
        "normalized_name": "shopping",
        "parent_category_id": None,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000007"),
        "name": "Electronics",
        "normalized_name": "electronics",
        "parent_category_id": None,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000008"),
        "name": "Education",
        "normalized_name": "education",
        "parent_category_id": None,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000009"),
        "name": "Entertainment",
        "normalized_name": "entertainment",
        "parent_category_id": None,
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000010"),
        "name": "Work Expense",
        "normalized_name": "work expense",
        "parent_category_id": None,
    },
)


def upgrade() -> None:
    """Create the Phase 1 tables, integrity rules, indexes, and reference data."""
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "default_currency",
            sa.String(length=3),
            server_default=sa.text("'INR'"),
            nullable=False,
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'UTC'"),
            nullable=False,
        ),
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
            "default_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_users_default_currency_format"),
        ),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND char_length(email) > 3",
            name=op.f("ck_users_email_normalized"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0",
            name=op.f("ck_users_name_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(timezone)) > 0",
            name=op.f("ck_users_timezone_not_blank"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "merchants",
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=True),
        sa.Column("merchant_category", sa.String(length=80), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name=op.f("ck_merchants_display_name_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalized_name)) > 0",
            name=op.f("ck_merchants_normalized_name_not_blank"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchants")),
        sa.UniqueConstraint(
            "normalized_name",
            name="uq_merchants_normalized_name",
        ),
    )

    op.create_table(
        "categories",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("normalized_name", sa.String(length=80), nullable=False),
        sa.Column("parent_category_id", sa.Uuid(), nullable=True),
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
            "char_length(btrim(name)) > 0",
            name=op.f("ck_categories_name_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalized_name)) > 0",
            name=op.f("ck_categories_normalized_name_not_blank"),
        ),
        sa.CheckConstraint(
            "parent_category_id IS NULL OR parent_category_id <> id",
            name=op.f("ck_categories_parent_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_category_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_categories_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_categories_user_normalized_name",
        ),
    )
    op.create_index(
        "ix_categories_user_parent",
        "categories",
        ["user_id", "parent_category_id"],
        unique=False,
    )
    op.create_index(
        "uq_categories_system_normalized_name",
        "categories",
        ["normalized_name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )

    op.create_table(
        "transactions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "transaction_type",
            sa.Enum(
                "expense",
                "income",
                "transfer",
                "refund",
                "shared_expense",
                name="transaction_type",
                native_enum=False,
                create_constraint=True,
                length=14,
            ),
            nullable=False,
        ),
        sa.Column("merchant_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                name="transaction_source",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "posted",
                "voided",
                name="transaction_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default=sa.text("'posted'"),
            nullable=False,
        ),
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
            "amount > 0",
            name=op.f("ck_transactions_amount_positive"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_transactions_confidence_range"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_transactions_currency_format"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(description)) > 0",
            name=op.f("ck_transactions_description_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_transactions_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.id"],
            name=op.f("fk_transactions_merchant_id_merchants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_transactions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_transactions_id_user",
        ),
    )
    op.create_index(
        "ix_transactions_user_category_date",
        "transactions",
        ["user_id", "category_id", "transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_user_date_id",
        "transactions",
        [
            "user_id",
            sa.literal_column("transaction_date DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_transactions_user_merchant_date",
        "transactions",
        ["user_id", "merchant_id", "transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_user_status_date",
        "transactions",
        ["user_id", "status", "transaction_date"],
        unique=False,
    )

    op.create_table(
        "people",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
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
            "char_length(btrim(name)) > 0",
            name=op.f("ck_people_name_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalized_name)) > 0",
            name=op.f("ck_people_normalized_name_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_people_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
        sa.UniqueConstraint("id", "user_id", name="uq_people_id_user"),
        sa.UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_people_user_normalized_name",
        ),
    )

    _create_obligation_table("receivables")
    _create_obligation_table("payables")

    op.create_table(
        "recurring_payments",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "recurrence_rule",
            sa.Enum(
                "weekly",
                "monthly",
                "quarterly",
                "yearly",
                name="recurrence_rule",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("next_expected_date", sa.Date(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "paused",
                "ended",
                "needs_review",
                name="recurring_payment_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
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
            "amount > 0",
            name=op.f("ck_recurring_payments_amount_positive"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_recurring_payments_confidence_range"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_recurring_payments_currency_format"),
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.id"],
            name=op.f("fk_recurring_payments_merchant_id_merchants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recurring_payments_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_payments")),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_recurring_payments_id_user",
        ),
    )
    op.create_index(
        "ix_recurring_payments_user_status_next",
        "recurring_payments",
        ["user_id", "status", "next_expected_date", "id"],
        unique=False,
    )

    op.create_table(
        "obligation_settlements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("receivable_id", sa.Uuid(), nullable=True),
        sa.Column("payable_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0",
            name=op.f("ck_obligation_settlements_amount_positive"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_obligation_settlements_currency_format"),
        ),
        sa.CheckConstraint(
            "(receivable_id IS NULL) <> (payable_id IS NULL)",
            name=op.f("ck_obligation_settlements_exactly_one_obligation"),
        ),
        sa.ForeignKeyConstraint(
            ["payable_id", "user_id", "currency"],
            ["payables.id", "payables.user_id", "payables.currency"],
            name="fk_settlements_payable_owner_currency",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receivable_id", "user_id", "currency"],
            ["receivables.id", "receivables.user_id", "receivables.currency"],
            name="fk_settlements_receivable_owner_currency",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_settlements_transaction_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_obligation_settlements_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_obligation_settlements"),
        ),
    )
    op.create_index(
        "ix_settlements_payable",
        "obligation_settlements",
        ["payable_id"],
        unique=False,
        postgresql_where=sa.text("payable_id IS NOT NULL"),
    )
    op.create_index(
        "ix_settlements_receivable",
        "obligation_settlements",
        ["receivable_id"],
        unique=False,
        postgresql_where=sa.text("receivable_id IS NOT NULL"),
    )

    category_table = sa.table(
        "categories",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("normalized_name", sa.String()),
        sa.column("parent_category_id", sa.Uuid()),
    )
    op.bulk_insert(
        category_table,
        [
            {
                **category,
                "user_id": None,
            }
            for category in SYSTEM_CATEGORIES
        ],
    )

    _create_category_scope_triggers()


def downgrade() -> None:
    """Remove all Phase 1 data and schema objects."""
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_category_scope ON transactions")
    op.execute("DROP FUNCTION IF EXISTS spendgraph_enforce_transaction_category_scope()")
    op.execute("DROP TRIGGER IF EXISTS trg_categories_parent_scope ON categories")
    op.execute("DROP FUNCTION IF EXISTS spendgraph_enforce_category_parent_scope()")

    op.drop_index(
        "ix_settlements_receivable",
        table_name="obligation_settlements",
        postgresql_where=sa.text("receivable_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_settlements_payable",
        table_name="obligation_settlements",
        postgresql_where=sa.text("payable_id IS NOT NULL"),
    )
    op.drop_table("obligation_settlements")

    op.drop_index(
        "ix_recurring_payments_user_status_next",
        table_name="recurring_payments",
    )
    op.drop_table("recurring_payments")

    _drop_obligation_table("payables")
    _drop_obligation_table("receivables")
    op.drop_table("people")

    op.drop_index(
        "ix_transactions_user_status_date",
        table_name="transactions",
    )
    op.drop_index(
        "ix_transactions_user_merchant_date",
        table_name="transactions",
    )
    op.drop_index("ix_transactions_user_date_id", table_name="transactions")
    op.drop_index(
        "ix_transactions_user_category_date",
        table_name="transactions",
    )
    op.drop_table("transactions")

    op.drop_index(
        "uq_categories_system_normalized_name",
        table_name="categories",
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.drop_index("ix_categories_user_parent", table_name="categories")
    op.drop_table("categories")
    op.drop_table("merchants")
    op.drop_table("users")


def _create_obligation_table(table_name: str) -> None:
    op.create_table(
        table_name,
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("issued_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "partially_paid",
                "paid",
                "overdue",
                "cancelled",
                name="obligation_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
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
            "amount > 0",
            name=op.f(f"ck_{table_name}_amount_positive"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f(f"ck_{table_name}_confidence_range"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name=op.f(f"ck_{table_name}_currency_format"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(description)) > 0",
            name=op.f(f"ck_{table_name}_description_not_blank"),
        ),
        sa.CheckConstraint(
            "due_date IS NULL OR due_date >= issued_date",
            name=op.f(f"ck_{table_name}_due_not_before_issued"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id", "user_id"],
            ["people.id", "people.user_id"],
            name=f"fk_{table_name}_person_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name=f"fk_{table_name}_transaction_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f(f"fk_{table_name}_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table_name}")),
        sa.UniqueConstraint(
            "id",
            "user_id",
            "currency",
            name=f"uq_{table_name}_id_user_currency",
        ),
    )
    op.create_index(
        f"ix_{table_name}_user_issued_id",
        table_name,
        [
            "user_id",
            sa.literal_column("issued_date DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        f"ix_{table_name}_user_status_due",
        table_name,
        ["user_id", "status", "due_date", "id"],
        unique=False,
    )


def _drop_obligation_table(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_user_status_due", table_name=table_name)
    op.drop_index(f"ix_{table_name}_user_issued_id", table_name=table_name)
    op.drop_table(table_name)


def _create_category_scope_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION spendgraph_enforce_category_parent_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_owner uuid;
            makes_cycle boolean;
        BEGIN
            IF NEW.parent_category_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT user_id
            INTO parent_owner
            FROM categories
            WHERE id = NEW.parent_category_id;

            IF NOT FOUND THEN
                RETURN NEW;
            END IF;

            IF parent_owner IS NOT NULL
               AND parent_owner IS DISTINCT FROM NEW.user_id THEN
                RAISE EXCEPTION
                    'category parent is not visible to this category owner'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_categories_parent_owner';
            END IF;

            WITH RECURSIVE ancestors(id, parent_category_id) AS (
                SELECT id, parent_category_id
                FROM categories
                WHERE id = NEW.parent_category_id
                UNION
                SELECT category.id, category.parent_category_id
                FROM categories AS category
                JOIN ancestors
                  ON category.id = ancestors.parent_category_id
            )
            SELECT EXISTS (
                SELECT 1
                FROM ancestors
                WHERE id = NEW.id
            )
            INTO makes_cycle;

            IF makes_cycle THEN
                RAISE EXCEPTION
                    'category hierarchy cannot contain a cycle'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_categories_parent_cycle';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_categories_parent_scope
        BEFORE INSERT OR UPDATE OF user_id, parent_category_id
        ON categories
        FOR EACH ROW
        EXECUTE FUNCTION spendgraph_enforce_category_parent_scope()
        """
    )
    op.execute(
        """
        CREATE FUNCTION spendgraph_enforce_transaction_category_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            category_owner uuid;
        BEGIN
            IF NEW.category_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT user_id
            INTO category_owner
            FROM categories
            WHERE id = NEW.category_id;

            IF FOUND
               AND category_owner IS NOT NULL
               AND category_owner IS DISTINCT FROM NEW.user_id THEN
                RAISE EXCEPTION
                    'transaction category is owned by another user'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_transactions_category_owner';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_transactions_category_scope
        BEFORE INSERT OR UPDATE OF user_id, category_id
        ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION spendgraph_enforce_transaction_category_scope()
        """
    )
