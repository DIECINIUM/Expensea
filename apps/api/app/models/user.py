"""User-owned ledger profile."""

from sqlalchemy import CheckConstraint, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Profile and user-calendar defaults for one ledger owner."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "email = lower(btrim(email)) AND char_length(email) > 3",
            name="email_normalized",
        ),
        CheckConstraint(
            "char_length(btrim(name)) > 0",
            name="name_not_blank",
        ),
        CheckConstraint(
            "default_currency ~ '^[A-Z]{3}$'",
            name="default_currency_format",
        ),
        CheckConstraint(
            "char_length(btrim(timezone)) > 0",
            name="timezone_not_blank",
        ),
    )

    email: Mapped[str] = mapped_column(String(254), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    default_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default=text("'INR'"),
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="UTC",
        server_default=text("'UTC'"),
    )
