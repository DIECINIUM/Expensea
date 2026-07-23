"""Manually managed expected recurring payments."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
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
    RecurrenceRule,
    RecurringPaymentStatus,
    enum_values,
)


class RecurringPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One expected payment managed directly by its ledger owner."""

    __tablename__ = "recurring_payments"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_recurring_payments_id_user"),
        CheckConstraint(
            "amount > 0",
            name="amount_positive",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_format",
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
    merchant_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    recurrence_rule: Mapped[RecurrenceRule] = mapped_column(
        Enum(
            RecurrenceRule,
            name="recurrence_rule",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
    )
    next_expected_date: Mapped[date] = mapped_column(Date, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4, asdecimal=True),
    )
    status: Mapped[RecurringPaymentStatus] = mapped_column(
        Enum(
            RecurringPaymentStatus,
            name="recurring_payment_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=RecurringPaymentStatus.ACTIVE,
        server_default=text("'active'"),
    )


Index(
    "ix_recurring_payments_user_status_next",
    RecurringPayment.user_id,
    RecurringPayment.status,
    RecurringPayment.next_expected_date,
    RecurringPayment.id,
)
