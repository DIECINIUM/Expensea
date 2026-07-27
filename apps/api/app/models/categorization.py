"""Owner-scoped categorization rules, learned mappings, and correction audit."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CategoryRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "category_rules"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_pattern", name="uq_category_rules_user_pattern"),
        ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        CheckConstraint("char_length(btrim(normalized_pattern)) > 0", name="pattern_not_blank"),
        Index("ix_category_rules_user_enabled_priority", "user_id", "enabled", "priority"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    normalized_pattern: Mapped[str] = mapped_column(String(120), nullable=False)
    category_id: Mapped[UUID] = mapped_column(nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class MerchantCategoryMap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchant_category_maps"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant_id", name="uq_merchant_category_maps_user_merchant"),
        Index("ix_merchant_category_maps_user_merchant", "user_id", "merchant_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    merchant_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class UserCorrection(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "user_corrections"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(normalized_description)) > 0", name="description_not_blank"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index(
            "ix_user_corrections_user_description_created",
            "user_id",
            "normalized_description",
            "created_at",
        ),
        Index(
            "ix_user_corrections_user_transaction_created",
            "user_id",
            "transaction_id",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_user_corrections_transaction_user",
            ondelete="RESTRICT",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    transaction_id: Mapped[UUID] = mapped_column(nullable=False)
    previous_category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    corrected_category_id: Mapped[UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    merchant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT")
    )
    normalized_description: Mapped[str] = mapped_column(String(500), nullable=False)
    classifier_version: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(nullable=False)
