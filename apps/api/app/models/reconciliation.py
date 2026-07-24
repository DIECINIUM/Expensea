"""Explainable duplicate decisions and append-only reconciliation actions."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import (
    ReconciliationActionType,
    ReconciliationDecision,
    ReconciliationStatus,
    enum_values,
)


class ReconciliationCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One normalized transaction event's duplicate-decision lifecycle."""

    __tablename__ = "reconciliation_cases"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_reconciliation_cases_id_user"),
        UniqueConstraint(
            "normalized_event_id",
            name="uq_reconciliation_cases_normalized_event",
        ),
        ForeignKeyConstraint(
            ["normalized_event_id", "raw_event_id", "user_id"],
            [
                "normalized_financial_events.id",
                "normalized_financial_events.raw_event_id",
                "normalized_financial_events.user_id",
            ],
            name="fk_reconciliation_cases_normalized_raw_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["candidate_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_cases_candidate_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["resulting_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_cases_resulting_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 1",
            name="score_range",
        ),
        CheckConstraint(
            "jsonb_typeof(reasons) = 'array'",
            name="reasons_array",
        ),
        CheckConstraint(
            "jsonb_typeof(evidence_locator) = 'object'",
            name="evidence_locator_object",
        ),
        CheckConstraint(
            "evidence_excerpt IS NULL OR char_length(evidence_excerpt) <= 500",
            name="evidence_excerpt_bounded",
        ),
        CheckConstraint(
            "char_length(btrim(score_version)) > 0",
            name="score_version_not_blank",
        ),
        CheckConstraint(
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
            name="status_targets_consistent",
        ),
        CheckConstraint(
            "(initial_decision = 'merge' AND status IN ('merged', 'unmerged')) OR "
            "(initial_decision = 'possible_duplicate') OR "
            "(initial_decision = 'new_transaction' AND status = 'kept_separate')",
            name="initial_decision_lifecycle",
        ),
        Index(
            "ix_reconciliation_cases_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_reconciliation_cases_user_candidate",
            "user_id",
            "candidate_transaction_id",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    normalized_event_id: Mapped[UUID] = mapped_column(nullable=False)
    raw_event_id: Mapped[UUID] = mapped_column(nullable=False)
    candidate_transaction_id: Mapped[UUID | None]
    resulting_transaction_id: Mapped[UUID | None]
    initial_decision: Mapped[ReconciliationDecision] = mapped_column(
        Enum(
            ReconciliationDecision,
            name="reconciliation_decision",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=20,
        ),
        nullable=False,
    )
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(
            ReconciliationStatus,
            name="reconciliation_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
    )
    score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4, asdecimal=True),
        nullable=False,
    )
    score_version: Mapped[str] = mapped_column(String(40), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    evidence_locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    evidence_excerpt: Mapped[str | None] = mapped_column(String(500))


class ReconciliationAction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Insert-only audit entry for one reconciliation state transition."""

    __tablename__ = "reconciliation_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "user_id"],
            ["reconciliation_cases.id", "reconciliation_cases.user_id"],
            name="fk_reconciliation_actions_case_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["from_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_actions_from_transaction_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["to_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_reconciliation_actions_to_transaction_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 1",
            name="score_range",
        ),
        CheckConstraint(
            "jsonb_typeof(reasons) = 'array'",
            name="reasons_array",
        ),
        Index(
            "ix_reconciliation_actions_case_created",
            "case_id",
            "created_at",
        ),
        Index(
            "ix_reconciliation_actions_user_created",
            "user_id",
            "created_at",
        ),
    )

    case_id: Mapped[UUID] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    action_type: Mapped[ReconciliationActionType] = mapped_column(
        Enum(
            ReconciliationActionType,
            name="reconciliation_action_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=24,
        ),
        nullable=False,
    )
    from_transaction_id: Mapped[UUID | None]
    to_transaction_id: Mapped[UUID | None]
    score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4, asdecimal=True),
        nullable=False,
    )
    reasons: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
