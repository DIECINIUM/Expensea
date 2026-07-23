"""Canonical merchants and hierarchical ledger categories."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Merchant(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Canonical merchant reference data shared across ledger owners."""

    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_merchants_normalized_name"),
        CheckConstraint(
            "char_length(btrim(normalized_name)) > 0",
            name="normalized_name_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="display_name_not_blank",
        ),
    )

    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(253))
    merchant_category: Mapped[str | None] = mapped_column(String(80))


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """System or user-owned node in the category hierarchy."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_categories_user_normalized_name",
        ),
        CheckConstraint(
            "char_length(btrim(name)) > 0",
            name="name_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(normalized_name)) > 0",
            name="normalized_name_not_blank",
        ),
        CheckConstraint(
            "parent_category_id IS NULL OR parent_category_id <> id",
            name="parent_not_self",
        ),
        Index(
            "uq_categories_system_normalized_name",
            "normalized_name",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
        Index("ix_categories_user_parent", "user_id", "parent_category_id"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(80), nullable=False)
    parent_category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
    )
