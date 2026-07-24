"""Unit tests for connector contracts, identity, registry, and state."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.connectors.contracts import ConnectorEnvelope
from app.connectors.mock_receipt import MockReceiptConnector
from app.connectors.registry import ConnectorRegistry
from app.domain.enums import ConnectorType, NormalizedEventKind, RawEventState
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.errors import IngestionConflictError
from app.ingestion.identity import content_sha256, event_identity_key
from app.ingestion.state import require_state_transition

OCCURRED_AT = datetime(2026, 7, 24, 8, 30, tzinfo=UTC)


def test_normalized_contract_preserves_exact_money_and_bounds_tags() -> None:
    event = NormalizedFinancialEventV1.model_validate(
        {
            "event_kind": "expense",
            "amount": "499.1250",
            "currency": "inr",
            "description": "  Cloud   renewal ",
            "occurred_at": "2026-07-24T14:00:00+05:30",
            "merchant_name": " Example   Cloud ",
            "category_hint": " Work Expense ",
            "tags": ["Subscription", " subscription ", "Work"],
            "confidence": "0.9500",
        }
    )

    assert event.event_kind is NormalizedEventKind.EXPENSE
    assert event.amount == Decimal("499.1250")
    assert event.currency == "INR"
    assert event.description == "Cloud renewal"
    assert event.occurred_at == datetime(2026, 7, 24, 8, 30, tzinfo=UTC)
    assert event.tags == ("Subscription", "Work")
    assert event.confidence == Decimal("0.9500")


@pytest.mark.parametrize(
    "values",
    [
        {
            "event_kind": "expense",
            "amount": "10.00",
            "description": "Missing currency",
        },
        {
            "event_kind": "expense",
            "currency": "INR",
            "description": "Missing amount",
        },
        {
            "event_kind": "expense",
            "amount": "10.00",
            "currency": "XYZ",
            "description": "Unsupported currency",
        },
        {
            "event_kind": "expense",
            "description": "Naive date",
            "occurred_at": "2026-07-24T08:30:00",
        },
    ],
)
def test_normalized_contract_rejects_unsafe_or_incomplete_pairs(
    values: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        NormalizedFinancialEventV1.model_validate(values)


def test_content_identity_is_canonical_and_prefers_external_id() -> None:
    first = ConnectorEnvelope(
        event_type="receipt",
        occurred_at=OCCURRED_AT,
        payload={"currency": "INR", "amount": "10.00"},
    )
    reordered = ConnectorEnvelope(
        event_type="receipt",
        occurred_at=OCCURRED_AT,
        payload={"amount": "10.00", "currency": "INR"},
    )

    first_hash = content_sha256(first)

    assert first_hash == content_sha256(reordered)
    assert event_identity_key(first, content_hash=first_hash) == f"sha256:{first_hash}"

    external = first.model_copy(update={"external_event_id": "gmail-message-1"})
    assert event_identity_key(external, content_hash=first_hash) == "external:gmail-message-1"


def test_registry_rejects_duplicate_connector_keys() -> None:
    connector = MockReceiptConnector(())
    registry = ConnectorRegistry([connector])

    assert registry.get(ConnectorType.MOCK_RECEIPT) is connector
    assert registry.descriptors() == (connector.descriptor,)
    with pytest.raises(IngestionConflictError) as exc_info:
        registry.register(MockReceiptConnector(()))
    assert exc_info.value.code == "CONNECTOR_ALREADY_REGISTERED"


def test_processing_state_machine_allows_retry_but_not_terminal_rewrite() -> None:
    require_state_transition(RawEventState.RECEIVED, RawEventState.FAILED)
    require_state_transition(RawEventState.FAILED, RawEventState.NORMALIZED)
    require_state_transition(RawEventState.NORMALIZED, RawEventState.PROCESSED)

    with pytest.raises(IngestionConflictError) as exc_info:
        require_state_transition(RawEventState.PROCESSED, RawEventState.FAILED)
    assert exc_info.value.code == "INVALID_INGESTION_STATE_TRANSITION"
