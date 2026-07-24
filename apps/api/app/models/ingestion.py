"""Replay-safe source ingestion, normalized events, and ledger evidence."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
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

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import (
    ConnectorType,
    EvidenceKind,
    NormalizedEventKind,
    RawEventState,
    SourceConnectionStatus,
    enum_values,
)


class SourceConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One user-owned, non-secret source configuration."""

    __tablename__ = "source_connections"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_source_connections_id_user"),
        UniqueConstraint(
            "user_id",
            "connector_type",
            "connection_key",
            name="uq_source_connections_user_connector_key",
        ),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="display_name_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(connection_key)) > 0",
            name="connection_key_not_blank",
        ),
        Index(
            "ix_source_connections_user_status",
            "user_id",
            "status",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    connector_type: Mapped[ConnectorType] = mapped_column(
        Enum(
            ConnectorType,
            name="connector_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=24,
        ),
        nullable=False,
    )
    connection_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[SourceConnectionStatus] = mapped_column(
        Enum(
            SourceConnectionStatus,
            name="source_connection_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=SourceConnectionStatus.ACTIVE,
        server_default=text("'active'"),
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    cursor: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class RawEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Insert-only minimized source data with a deterministic delivery identity."""

    __tablename__ = "raw_events"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_raw_events_id_user"),
        UniqueConstraint(
            "source_connection_id",
            "identity_key",
            name="uq_raw_events_connection_identity",
        ),
        ForeignKeyConstraint(
            ["source_connection_id", "user_id"],
            ["source_connections.id", "source_connections.user_id"],
            name="fk_raw_events_connection_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "char_length(btrim(identity_key)) > 0",
            name="identity_key_not_blank",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="content_sha256_format",
        ),
        CheckConstraint(
            "char_length(btrim(source_event_type)) > 0",
            name="source_event_type_not_blank",
        ),
        Index(
            "ix_raw_events_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_raw_events_connection_created",
            "source_connection_id",
            "created_at",
        ),
        Index(
            "ix_raw_events_connection_content_hash",
            "source_connection_id",
            "content_sha256",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(nullable=False)
    source_connection_id: Mapped[UUID] = mapped_column(nullable=False)
    identity_key: Mapped[str] = mapped_column(String(320), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class RawEventProcessing(TimestampMixin, Base):
    """Mutable state separated from immutable raw-event source fields."""

    __tablename__ = "raw_event_processing"
    __table_args__ = (
        ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_raw_event_processing_event_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        Index(
            "ix_raw_event_processing_user_state",
            "user_id",
            "state",
            "updated_at",
        ),
    )

    raw_event_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    state: Mapped[RawEventState] = mapped_column(
        Enum(
            RawEventState,
            name="raw_event_state",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
        default=RawEventState.RECEIVED,
        server_default=text("'received'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class NormalizedFinancialEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Versioned provider-neutral financial event produced from one raw event."""

    __tablename__ = "normalized_financial_events"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "raw_event_id",
            "user_id",
            name="uq_normalized_events_id_raw_user",
        ),
        UniqueConstraint(
            "raw_event_id",
            "schema_version",
            "normalizer_key",
            "normalizer_version",
            name="uq_normalized_events_raw_contract",
        ),
        ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_normalized_events_raw_user",
            ondelete="RESTRICT",
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
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint(
            "char_length(btrim(schema_version)) > 0",
            name="schema_version_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(normalizer_key)) > 0",
            name="normalizer_key_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(normalizer_version)) > 0",
            name="normalizer_version_not_blank",
        ),
        Index(
            "ix_normalized_events_user_kind_occurred",
            "user_id",
            "event_kind",
            "occurred_at",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(nullable=False)
    raw_event_id: Mapped[UUID] = mapped_column(nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    normalizer_key: Mapped[str] = mapped_column(String(80), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(40), nullable=False)
    event_kind: Mapped[NormalizedEventKind] = mapped_column(
        Enum(
            NormalizedEventKind,
            name="normalized_event_kind",
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
    merchant_name: Mapped[str | None] = mapped_column(String(160))
    counterparty: Mapped[str | None] = mapped_column(String(160))
    category_hint: Mapped[str | None] = mapped_column(String(80))
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4, asdecimal=True),
    )


class Evidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Bounded provenance linking one accepted normalized event to the ledger."""

    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint(
            "normalized_event_id",
            name="uq_evidence_normalized_event",
        ),
        ForeignKeyConstraint(
            ["raw_event_id", "user_id"],
            ["raw_events.id", "raw_events.user_id"],
            name="fk_evidence_raw_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["normalized_event_id", "raw_event_id", "user_id"],
            [
                "normalized_financial_events.id",
                "normalized_financial_events.raw_event_id",
                "normalized_financial_events.user_id",
            ],
            name="fk_evidence_normalized_raw_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            name="fk_evidence_transaction_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "excerpt IS NULL OR char_length(excerpt) <= 500",
            name="excerpt_bounded",
        ),
        Index(
            "ix_evidence_user_transaction",
            "user_id",
            "transaction_id",
        ),
        Index(
            "ix_evidence_user_raw_event",
            "user_id",
            "raw_event_id",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(nullable=False)
    raw_event_id: Mapped[UUID] = mapped_column(nullable=False)
    normalized_event_id: Mapped[UUID] = mapped_column(nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_kind: Mapped[EvidenceKind] = mapped_column(
        Enum(
            EvidenceKind,
            name="evidence_kind",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=20,
        ),
        nullable=False,
        default=EvidenceKind.SOURCE_EVENT,
        server_default=text("'source_event'"),
    )
    locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    excerpt: Mapped[str | None] = mapped_column(String(500))
