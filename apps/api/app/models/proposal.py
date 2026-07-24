"""Review-first AI extraction proposals with canonical target provenance."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import (
    NormalizedEventKind,
    ProposalStatus,
    RecurrenceRule,
    enum_values,
)


class FinancialEventProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Schema-valid but untrusted event awaiting explicit user review."""

    __tablename__ = "financial_event_proposals"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="uq_financial_event_proposals_id_user",
        ),
        UniqueConstraint(
            "raw_event_id",
            "prompt_name",
            "prompt_version",
            "schema_version",
            name="uq_financial_event_proposals_raw_prompt",
        ),
        ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_financial_event_proposals_raw_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_financial_event_proposals_transaction_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["receivable_id", "user_id", "currency"],
            ["receivables.id", "receivables.user_id", "receivables.currency"],
            name="fk_financial_event_proposals_receivable_owner_currency",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["payable_id", "user_id", "currency"],
            ["payables.id", "payables.user_id", "payables.currency"],
            name="fk_financial_event_proposals_payable_owner_currency",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recurring_payment_id", "user_id"],
            ["recurring_payments.id", "recurring_payments.user_id"],
            name="fk_financial_event_proposals_recurring_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(amount IS NULL) = (currency IS NULL)",
            name="money_pair_complete",
        ),
        CheckConstraint(
            "amount IS NULL OR amount > 0",
            name="amount_positive_when_present",
        ),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="currency_format_when_present",
        ),
        CheckConstraint(
            "char_length(btrim(description)) > 0",
            name="description_not_blank",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_range",
        ),
        CheckConstraint(
            "jsonb_typeof(tags) = 'array'",
            name="tags_array",
        ),
        CheckConstraint(
            "jsonb_typeof(review_reasons) = 'array'",
            name="review_reasons_array",
        ),
        CheckConstraint("latency_ms >= 0", name="latency_non_negative"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="output_tokens_non_negative",
        ),
        CheckConstraint(
            "num_nonnulls(transaction_id, receivable_id, payable_id, recurring_payment_id) <= 1",
            name="at_most_one_canonical_target",
        ),
        CheckConstraint(
            "(status = 'approved' AND "
            "num_nonnulls(transaction_id, receivable_id, payable_id, "
            "recurring_payment_id) = 1) OR "
            "(status <> 'approved' AND "
            "num_nonnulls(transaction_id, receivable_id, payable_id, "
            "recurring_payment_id) = 0)",
            name="approved_has_canonical_target",
        ),
        Index(
            "ix_financial_event_proposals_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_financial_event_proposals_user_raw",
            "user_id",
            "raw_event_id",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(nullable=False)
    raw_event_id: Mapped[UUID] = mapped_column(nullable=False)
    event_kind: Mapped[NormalizedEventKind] = mapped_column(
        Enum(
            NormalizedEventKind,
            name="proposal_event_kind",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
    )
    amount: Mapped[Decimal | None]
    currency: Mapped[str | None] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date | None] = mapped_column(Date)
    merchant_name: Mapped[str | None] = mapped_column(String(160))
    counterparty: Mapped[str | None] = mapped_column(String(160))
    recurrence_rule: Mapped[RecurrenceRule | None] = mapped_column(
        Enum(
            RecurrenceRule,
            name="proposal_recurrence_rule",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        )
    )
    next_expected_date: Mapped[date | None] = mapped_column(Date)
    category_hint: Mapped[str | None] = mapped_column(String(80))
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4, asdecimal=True),
        nullable=False,
    )
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(
            ProposalStatus,
            name="proposal_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=ProposalStatus.NEEDS_REVIEW,
        server_default=text("'needs_review'"),
    )
    review_reasons: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    transaction_id: Mapped[UUID | None]
    receivable_id: Mapped[UUID | None]
    payable_id: Mapped[UUID | None]
    recurring_payment_id: Mapped[UUID | None]
