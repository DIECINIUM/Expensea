"""Persisted Phase 1 ledger vocabularies."""

from enum import StrEnum


def enum_values[EnumType: StrEnum](enum_type: type[EnumType]) -> list[str]:
    """Persist stable enum values rather than Python member names."""
    return [member.value for member in enum_type]


class TransactionType(StrEnum):
    """Economic direction of a ledger transaction."""

    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    REFUND = "refund"
    SHARED_EXPENSE = "shared_expense"


class TransactionStatus(StrEnum):
    """Posting lifecycle for a ledger transaction."""

    PENDING = "pending"
    POSTED = "posted"
    VOIDED = "voided"


class TransactionSource(StrEnum):
    """Normalized origin of a transaction in the current phase."""

    MANUAL = "manual"
    INGESTION = "ingestion"


class ConnectorType(StrEnum):
    """Stable connector registry keys persisted with source connections."""

    MANUAL_NOTE = "manual_note"
    CSV_IMPORT = "csv_import"
    MOCK_RECEIPT = "mock_receipt"
    GMAIL = "gmail"
    GOOGLE_KEEP_TAKEOUT = "google_keep_takeout"


class SourceConnectionStatus(StrEnum):
    """Lifecycle of one user-owned source authorization or import channel."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class RawEventState(StrEnum):
    """Explicit replay-safe ingestion processing states."""

    RECEIVED = "received"
    NORMALIZED = "normalized"
    PROCESSED = "processed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class NormalizedEventKind(StrEnum):
    """Provider-neutral financial meanings produced by normalizers."""

    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    REFUND = "refund"
    SHARED_EXPENSE = "shared_expense"
    RECEIVABLE = "receivable"
    PAYABLE = "payable"
    RECURRING = "recurring"
    UNKNOWN = "unknown"


class EvidenceKind(StrEnum):
    """How a canonical record is supported by source data."""

    SOURCE_EVENT = "source_event"


class ProposalStatus(StrEnum):
    """Human-review lifecycle for untrusted extracted financial events."""

    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ObligationStatus(StrEnum):
    """Settlement lifecycle for receivables and payables."""

    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class RecurrenceRule(StrEnum):
    """Manually managed recurrence rules supported in Phase 1."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RecurringPaymentStatus(StrEnum):
    """Lifecycle for an expected recurring payment."""

    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    NEEDS_REVIEW = "needs_review"
