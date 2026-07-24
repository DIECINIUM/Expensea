"""Bounded CSV connector contract tests."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.connectors.csv_import import (
    MAX_CSV_DOCUMENT_BYTES,
    CsvTransactionConnector,
    parse_csv_document,
)
from app.domain.enums import NormalizedEventKind
from app.ingestion.errors import ConnectorContentError


@pytest.mark.asyncio
async def test_csv_rows_normalize_exact_money_and_replay_with_offset() -> None:
    document = (
        "external_id,event_kind,amount,currency,description,occurred_at,"
        "merchant_name,category_hint,tags,confidence\n"
        "bank-1,expense,499.1250,INR,Cloud renewal,"
        "2026-07-24T14:00:00+05:30,Example Cloud,Work,"
        "subscription|cloud,0.9900\n"
        "bank-2,refund,50.0000,INR,Partial refund,"
        "2026-07-25T14:00:00+05:30,Example Cloud,Work,refund,1.0000\n"
    )
    connector = CsvTransactionConnector.from_document("transactions.csv", document)

    first = await connector.fetch({})
    replay = await connector.fetch(first.next_cursor)
    normalized = connector.normalize(first.events[0])

    assert len(first.events) == 2
    assert first.next_cursor == {"offset": 2}
    assert replay.events == ()
    assert normalized.event_kind is NormalizedEventKind.EXPENSE
    assert normalized.amount == Decimal("499.1250")
    assert normalized.currency == "INR"
    assert normalized.occurred_at == datetime(2026, 7, 24, 8, 30, tzinfo=UTC)
    assert normalized.tags == ("subscription", "cloud")
    assert first.events[0].locator["row"] == 2


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ("description\nMissing kind\n", "CSV_REQUIRED_COLUMNS_MISSING"),
        (
            "event_kind,description,secret\nexpense,Coffee,nope\n",
            "CSV_COLUMNS_UNSUPPORTED",
        ),
        (
            "event_kind,description,occurred_at\nexpense,Coffee,2026-07-24T10:00:00\n",
            "CSV_ROW_DATETIME_INVALID",
        ),
        (
            "event_kind,description\nexpense\n",
            "CSV_ROW_REQUIRED_VALUE_MISSING",
        ),
    ],
)
def test_csv_rejects_ambiguous_or_unsupported_shapes(
    document: str,
    code: str,
) -> None:
    with pytest.raises(ConnectorContentError) as exc_info:
        parse_csv_document("transactions.csv", document)
    assert exc_info.value.code == code


def test_csv_rejects_oversized_documents() -> None:
    with pytest.raises(ConnectorContentError) as exc_info:
        parse_csv_document(
            "transactions.csv",
            b"x" * (MAX_CSV_DOCUMENT_BYTES + 1),
        )
    assert exc_info.value.code == "CSV_DOCUMENT_TOO_LARGE"


def test_csv_normalizer_rejects_invalid_money_pair() -> None:
    events = parse_csv_document(
        "transactions.csv",
        "event_kind,amount,description\nexpense,10.0000,Coffee\n",
    )
    connector = CsvTransactionConnector.from_document(
        "transactions.csv",
        "event_kind,amount,description\nexpense,10.0000,Coffee\n",
    )

    with pytest.raises(ConnectorContentError) as exc_info:
        connector.normalize(events[0])
    assert exc_info.value.code == "CSV_ROW_INVALID"
