"""Official-path Gmail, Keep Takeout, and manual-note connector tests."""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.connectors.gmail import GmailReceiptConnector
from app.connectors.google_keep_takeout import (
    GoogleKeepTakeoutConnector,
    parse_keep_takeout_document,
)
from app.connectors.manual_note import ManualNoteConnector, create_manual_note_envelope
from app.domain.enums import NormalizedEventKind
from app.ingestion.errors import ConnectorContentError

OCCURRED_AT = datetime(2026, 7, 24, 8, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_gmail_fetch_minimizes_and_filters_financial_messages() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer fixture-value"
        if request.url.path.endswith("/messages"):
            assert request.url.params["maxResults"] == "25"
            assert "receipt" in request.url.params["q"]
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {"id": "financial-1", "threadId": "thread-1"},
                        {"id": "newsletter-1", "threadId": "thread-2"},
                    ],
                    "nextPageToken": "next-page",
                },
            )
        if request.url.path.endswith("/financial-1"):
            return httpx.Response(
                200,
                json=_gmail_message(
                    message_id="financial-1",
                    subject="Your Google Play subscription receipt",
                    sender="Google Play <payments-noreply@google.com>",
                    snippet="You paid INR 249. Next payment is in one month.",
                    body="<p>Monthly music subscription charged INR 249.</p>",
                ),
            )
        if request.url.path.endswith("/newsletter-1"):
            return httpx.Response(
                200,
                json=_gmail_message(
                    message_id="newsletter-1",
                    subject="Weekly product news",
                    sender="News <updates@example.test>",
                    snippet="Read this week's product updates.",
                    body="<p>New features and community stories.</p>",
                ),
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = GmailReceiptConnector(
            access_token="fixture-value",
            client=client,
            api_base_url="https://gmail.example.test",
            max_results=25,
        )
        batch = await connector.fetch({})

    assert len(batch.events) == 1
    assert batch.next_cursor == {"pageToken": "next-page"}
    envelope = batch.events[0]
    assert envelope.external_event_id == "financial-1"
    assert envelope.payload["subject"] == "Your Google Play subscription receipt"
    assert envelope.payload["sender_name"] == "Google Play"
    assert envelope.payload["sender_domain"] == "google.com"
    assert envelope.payload["tags"] == ["gmail", "receipt", "subscription"]
    assert "fixture-value" not in json.dumps(envelope.model_dump(mode="json"))
    assert "payments-noreply@google.com" not in json.dumps(envelope.model_dump(mode="json"))
    assert len(requests) == 3

    normalized = connector.normalize(envelope)
    assert normalized.event_kind is NormalizedEventKind.UNKNOWN
    assert normalized.merchant_name == "Google Play"
    assert normalized.tags == ("gmail", "receipt", "subscription")


@pytest.mark.asyncio
async def test_gmail_health_reports_invalid_authorization_without_credential_echo() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, json={"error": {"message": "invalid"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = GmailReceiptConnector(
            access_token="fixture-value",
            client=client,
            api_base_url="https://gmail.example.test",
        )
        health = await connector.health()

    assert health.status.value == "misconfigured"
    assert health.code == "GMAIL_AUTHORIZATION_INVALID"
    assert "fixture-value" not in repr(health)


def test_keep_takeout_import_preserves_note_labels_and_ignores_attachments() -> None:
    document = {
        "title": "Trip expenses",
        "textContent": "Paid ₹450 for airport cab",
        "listContent": [
            {"text": "Hotel ₹3,000", "isChecked": False},
            {"text": "Cab ₹450", "isChecked": True},
        ],
        "labels": [{"name": "Travel"}, {"name": " Expenses "}],
        "userEditedTimestampUsec": "1784881800000000",
        "attachments": [
            {
                "filePath": "sensitive-receipt.jpg",
                "mimetype": "image/jpeg",
            }
        ],
    }

    envelope = parse_keep_takeout_document(
        "Trip expenses.json",
        json.dumps(document),
    )

    assert envelope is not None
    assert envelope.external_event_id is not None
    assert "Trip expenses" not in envelope.external_event_id
    assert envelope.payload["title"] == "Trip expenses"
    assert "Hotel ₹3,000" in str(envelope.payload["note_text"])
    assert envelope.payload["labels"] == ["Travel", "Expenses"]
    assert "attachments" not in envelope.payload
    assert "sensitive-receipt.jpg" not in json.dumps(envelope.model_dump(mode="json"))

    connector = GoogleKeepTakeoutConnector([envelope])
    normalized = connector.normalize(envelope)
    assert normalized.event_kind is NormalizedEventKind.UNKNOWN
    assert normalized.tags == ("google-keep", "Travel", "Expenses")
    assert normalized.description == "Trip expenses"


@pytest.mark.asyncio
async def test_keep_takeout_connector_uses_replayable_offset_cursor() -> None:
    connector = GoogleKeepTakeoutConnector.from_documents(
        [
            (
                "one.json",
                json.dumps(
                    {
                        "title": "Expense one",
                        "textContent": "Paid ₹10",
                    }
                ),
            ),
            (
                "trashed.json",
                json.dumps(
                    {
                        "title": "Deleted expense",
                        "isTrashed": True,
                    }
                ),
            ),
        ]
    )

    first = await connector.fetch({})
    second = await connector.fetch(first.next_cursor)

    assert len(first.events) == 1
    assert first.next_cursor == {"offset": 1}
    assert second.events == ()


def test_keep_takeout_rejects_invalid_or_oversized_documents() -> None:
    with pytest.raises(ConnectorContentError) as invalid:
        parse_keep_takeout_document("invalid.json", "{not-json")
    assert invalid.value.code == "KEEP_DOCUMENT_INVALID"

    with pytest.raises(ConnectorContentError) as oversized:
        parse_keep_takeout_document("large.json", b"x" * 65_537)
    assert oversized.value.code == "KEEP_DOCUMENT_TOO_LARGE"


@pytest.mark.asyncio
async def test_manual_note_enters_unknown_review_contract_before_ai() -> None:
    envelope = create_manual_note_envelope(
        "  Lent   Priya ₹800 for a cab today  ",
        source_timestamp=OCCURRED_AT,
        note_id=UUID("b1000000-0000-4000-8000-000000000001"),
        labels=["Friend", " Travel "],
    )
    connector = ManualNoteConnector([envelope])
    batch = await connector.fetch({})
    normalized = connector.normalize(envelope)

    assert batch.events == (envelope,)
    assert envelope.payload["extraction_text"] == "Lent Priya ₹800 for a cab today"
    assert envelope.payload["labels"] == ["Friend", "Travel"]
    assert normalized.event_kind is NormalizedEventKind.UNKNOWN
    assert normalized.description == "Lent Priya ₹800 for a cab today"


def _gmail_message(
    *,
    message_id: str,
    subject: str,
    sender: str,
    snippet: str,
    body: str,
) -> dict[str, object]:
    encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "internalDate": "1784881800000",
        "snippet": snippet,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": "Fri, 24 Jul 2026 14:00:00 +0530"},
            ],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": encoded_body},
                }
            ],
        },
    }
