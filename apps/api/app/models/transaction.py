"""Canonical deterministic ledger transaction."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import (
    TransactionSource,
    TransactionStatus,
    TransactionType,
    enum_values,
)


class LedgerTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One user-owned economic event in the canonical ledger."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_transactions_id_user"),
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
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(
            TransactionType,
            name="transaction_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=14,
        ),
        nullable=False,
    )
    merchant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"),
    )
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source: Mapped[TransactionSource] = mapped_column(
        Enum(
            TransactionSource,
            name="transaction_source",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=TransactionSource.MANUAL,
        server_default=text("'manual'"),
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4, asdecimal=True),
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(
            TransactionStatus,
            name="transaction_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=TransactionStatus.POSTED,
        server_default=text("'posted'"),
    )


Index(
    "ix_transactions_user_date_id",
    LedgerTransaction.user_id,
    LedgerTransaction.transaction_date.desc(),
    LedgerTransaction.id.desc(),
)
Index(
    "ix_transactions_user_status_date",
    LedgerTransaction.user_id,
    LedgerTransaction.status,
    LedgerTransaction.transaction_date,
)
Index(
    "ix_transactions_user_category_date",
    LedgerTransaction.user_id,
    LedgerTransaction.category_id,
    LedgerTransaction.transaction_date,
)
Index(
    "ix_transactions_user_merchant_date",
    LedgerTransaction.user_id,
    LedgerTransaction.merchant_id,
    LedgerTransaction.transaction_date,
)
