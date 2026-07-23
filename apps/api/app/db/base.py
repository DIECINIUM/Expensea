"""Declarative metadata and deterministic numeric conventions."""

from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Financial values must enter application code as Decimal and persist as NUMERIC.
# Four fractional digits preserve source precision; display/currency rounding is a
# later, explicit domain operation and must never use binary floating point.
MONEY_PRECISION = 19
MONEY_SCALE = 4

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base for all future financial models and Alembic autogeneration."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        Decimal: Numeric(
            precision=MONEY_PRECISION,
            scale=MONEY_SCALE,
            asdecimal=True,
        )
    }


class UUIDPrimaryKeyMixin:
    """Application-generated UUID identity shared by persisted entities."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class CreatedAtMixin:
    """Database-generated creation instant."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TimestampMixin(CreatedAtMixin):
    """Creation and last-update instants for mutable entities."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
