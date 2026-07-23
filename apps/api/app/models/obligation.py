"""Receivables, payables, and immutable settlement history."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import ObligationStatus, enum_values


class Receivable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Original principal another person owes the ledger owner."""

    __tablename__ = "receivables"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            "currency",
            name="uq_receivables_id_user_currency",
        ),
        ForeignKeyConstraint(
            ["person_id", "user_id"],
            ["people.id", "people.user_id"],
            name="fk_receivables_person_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_receivables_transaction_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_format",
        ),
        CheckConstraint(
            "char_length(btrim(description)) > 0",
            name="description_not_blank",
        ),
        CheckConstraint(
            "due_date IS NULL OR due_date >= issued_date",
            name="due_not_before_issued",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    person_id: Mapped[UUID] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ObligationStatus] = mapped_column(
        Enum(
            ObligationStatus,
            name="obligation_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=ObligationStatus.OPEN,
        server_default=text("'open'"),
    )
    transaction_id: Mapped[UUID | None]
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4, asdecimal=True),
    )


class Payable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Original principal the ledger owner owes another person."""

    __tablename__ = "payables"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            "currency",
            name="uq_payables_id_user_currency",
        ),
        ForeignKeyConstraint(
            ["person_id", "user_id"],
            ["people.id", "people.user_id"],
            name="fk_payables_person_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_payables_transaction_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_format",
        ),
        CheckConstraint(
            "char_length(btrim(description)) > 0",
            name="description_not_blank",
        ),
        CheckConstraint(
            "due_date IS NULL OR due_date >= issued_date",
            name="due_not_before_issued",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    person_id: Mapped[UUID] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ObligationStatus] = mapped_column(
        Enum(
            ObligationStatus,
            name="obligation_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=ObligationStatus.OPEN,
        server_default=text("'open'"),
    )
    transaction_id: Mapped[UUID | None]
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4, asdecimal=True),
    )


class ObligationSettlement(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only partial or complete payment against one obligation."""

    __tablename__ = "obligation_settlements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receivable_id", "user_id", "currency"],
            ["receivables.id", "receivables.user_id", "receivables.currency"],
            name="fk_settlements_receivable_owner_currency",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["payable_id", "user_id", "currency"],
            ["payables.id", "payables.user_id", "payables.currency"],
            name="fk_settlements_payable_owner_currency",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_settlements_transaction_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(receivable_id IS NULL) <> (payable_id IS NULL)",
            name="exactly_one_obligation",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_format",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    receivable_id: Mapped[UUID | None]
    payable_id: Mapped[UUID | None]
    amount: Mapped[Decimal] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    transaction_id: Mapped[UUID | None]
    note: Mapped[str | None] = mapped_column(String(500))


Index(
    "ix_receivables_user_status_due",
    Receivable.user_id,
    Receivable.status,
    Receivable.due_date,
    Receivable.id,
)
Index(
    "ix_receivables_user_issued_id",
    Receivable.user_id,
    Receivable.issued_date.desc(),
    Receivable.id.desc(),
)
Index(
    "ix_payables_user_status_due",
    Payable.user_id,
    Payable.status,
    Payable.due_date,
    Payable.id,
)
Index(
    "ix_payables_user_issued_id",
    Payable.user_id,
    Payable.issued_date.desc(),
    Payable.id.desc(),
)
Index(
    "ix_settlements_receivable",
    ObligationSettlement.receivable_id,
    postgresql_where=ObligationSettlement.receivable_id.is_not(None),
)
Index(
    "ix_settlements_payable",
    ObligationSettlement.payable_id,
    postgresql_where=ObligationSettlement.payable_id.is_not(None),
)
