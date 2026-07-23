"""Private user-local people involved in obligations."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Person(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person known within exactly one user's ledger."""

    __tablename__ = "people"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_people_id_user"),
        UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_people_user_normalized_name",
        ),
        CheckConstraint(
            "char_length(btrim(name)) > 0",
            name="name_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(normalized_name)) > 0",
            name="normalized_name_not_blank",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
