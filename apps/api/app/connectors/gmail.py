"""Read-only Gmail receipt/subscription adapter with minimized message content."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.connectors.contracts import (
    ConnectorAuthorization,
    ConnectorBatch,
    ConnectorDescriptor,
    ConnectorEnvelope,
    ConnectorHealth,
    ConnectorHealthStatus,
)
from app.domain.enums import ConnectorType, NormalizedEventKind
from app.domain.normalization import normalize_display_text
from app.ingestion.contracts import NormalizedFinancialEventV1
from app.ingestion.errors import ConnectorContentError, ConnectorUnavailableError

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API_BASE_URL = "https://gmail.googleapis.com"
DEFAULT_FINANCIAL_QUERY = (
    "newer_than:2y "
    "{subject:(receipt invoice payment paid purchase order subscription renewal) "
    "from:(payments-noreply@google.com googleplay-noreply@google.com)}"
)
MAX_GMAIL_RESULTS = 50
MAX_BODY_CHARS = 6_000
MAX_SNIPPET_CHARS = 500
MAX_SUBJECT_CHARS = 300

_FINANCIAL_KEYWORDS = frozenset(
    {
        "amount",
        "bill",
        "charged",
        "invoice",
        "order",
        "paid",
        "payment",
        "purchase",
        "receipt",
        "renewal",
        "subscription",
        "transaction",
    }
)
_RECURRING_KEYWORDS = frozenset(
    {
        "annual",
        "auto-renew",
        "monthly",
        "next billing",
        "next payment",
        "recurring",
        "renewal",
        "subscription",
        "yearly",
    }
)


class _GmailMessageReference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    thread_id: str | None = Field(default=None, alias="threadId")


class _GmailListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    messages: list[_GmailMessageReference] = Field(default_factory=list)
    next_page_token: str | None = Field(default=None, alias="nextPageToken")


class _GmailHeader(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    value: str


class _GmailBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: str | None = None


class _GmailPart(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mime_type: str = Field(default="", alias="mimeType")
    body: _GmailBody = Field(default_factory=_GmailBody)
    headers: list[_GmailHeader] = Field(default_factory=list)
    parts: list[_GmailPart] = Field(default_factory=list)


class _GmailMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    thread_id: str | None = Field(default=None, alias="threadId")
    internal_date: str | None = Field(default=None, alias="internalDate")
    snippet: str = ""
    payload: _GmailPart


class GmailReceiptConnector:
    """Fetch likely financial messages using an ephemeral read-only access token."""

    _descriptor = ConnectorDescriptor(
        key=ConnectorType.GMAIL,
        display_name="Gmail receipts",
        authorization=ConnectorAuthorization.READ_ONLY_OAUTH,
        capabilities=("receipts", "transactions", "subscription-hints"),
    )

    def __init__(
        self,
        *,
        access_token: str,
        client: httpx.AsyncClient | None = None,
        api_base_url: str = GMAIL_API_BASE_URL,
        financial_query: str = DEFAULT_FINANCIAL_QUERY,
        max_results: int = MAX_GMAIL_RESULTS,
    ) -> None:
        if not access_token:
            raise ValueError("Gmail access token cannot be blank")
        if max_results < 1 or max_results > MAX_GMAIL_RESULTS:
            raise ValueError(f"max_results must be between 1 and {MAX_GMAIL_RESULTS}")
        self._access_token = access_token
        self._client = client
        self._api_base_url = api_base_url.rstrip("/")
        self._query = financial_query
        self._max_results = max_results

    @property
    def descriptor(self) -> ConnectorDescriptor:
        return self._descriptor

    async def health(self) -> ConnectorHealth:
        try:
            response = await self._get("/gmail/v1/users/me/profile")
        except httpx.HTTPError:
            return ConnectorHealth(
                status=ConnectorHealthStatus.UNAVAILABLE,
                code="GMAIL_API_UNAVAILABLE",
            )
        if response.status_code in {401, 403}:
            return ConnectorHealth(
                status=ConnectorHealthStatus.MISCONFIGURED,
                code="GMAIL_AUTHORIZATION_INVALID",
            )
        if response.is_error:
            return ConnectorHealth(
                status=ConnectorHealthStatus.UNAVAILABLE,
                code="GMAIL_API_UNAVAILABLE",
            )
        return ConnectorHealth(status=ConnectorHealthStatus.HEALTHY)

    async def fetch(self, cursor: dict[str, Any]) -> ConnectorBatch:
        page_token = cursor.get("pageToken")
        if page_token is not None and not isinstance(page_token, str):
            raise ConnectorContentError(
                code="INVALID_CONNECTOR_CURSOR",
                message="The Gmail connector cursor is invalid.",
            )
        params = {
            "q": self._query,
            "maxResults": str(self._max_results),
        }
        if page_token:
            params["pageToken"] = page_token

        response = await self._get(
            "/gmail/v1/users/me/messages",
            params=params,
        )
        self._require_success(response)
        try:
            page = _GmailListResponse.model_validate_json(response.content)
        except ValidationError as exc:
            raise ConnectorUnavailableError(
                code="GMAIL_INVALID_LIST_RESPONSE",
                message="Gmail returned an invalid message-list response.",
            ) from exc

        envelopes: list[ConnectorEnvelope] = []
        for reference in page.messages:
            message_response = await self._get(
                f"/gmail/v1/users/me/messages/{reference.id}",
                params={"format": "full"},
            )
            self._require_success(message_response)
            try:
                message = _GmailMessage.model_validate_json(message_response.content)
            except ValidationError as exc:
                raise ConnectorUnavailableError(
                    code="GMAIL_INVALID_MESSAGE_RESPONSE",
                    message="Gmail returned an invalid message response.",
                ) from exc
            envelope = _minimize_message(message)
            if envelope is not None:
                envelopes.append(envelope)

        next_cursor: dict[str, Any] = {}
        if page.next_page_token:
            next_cursor["pageToken"] = page.next_page_token
        return ConnectorBatch(events=tuple(envelopes), next_cursor=next_cursor)

    def normalize(self, envelope: ConnectorEnvelope) -> NormalizedFinancialEventV1:
        subject = _payload_text(envelope.payload, "subject")
        sender_name = _payload_text(envelope.payload, "sender_name")
        tags = envelope.payload.get("tags", ["gmail"])
        if not isinstance(tags, list):
            tags = ["gmail"]
        return NormalizedFinancialEventV1(
            event_kind=NormalizedEventKind.UNKNOWN,
            description=subject or "Gmail financial message",
            occurred_at=envelope.occurred_at,
            merchant_name=sender_name,
            tags=tuple(tag for tag in tags if isinstance(tag, str)),
            confidence=None,
        )

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._access_token}"}
        if self._client is not None:
            return await self._client.get(
                f"{self._api_base_url}{path}",
                params=params,
                headers=headers,
                timeout=30,
            )
        async with httpx.AsyncClient() as client:
            return await client.get(
                f"{self._api_base_url}{path}",
                params=params,
                headers=headers,
                timeout=30,
            )

    @staticmethod
    def _require_success(response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise ConnectorUnavailableError(
                code="GMAIL_AUTHORIZATION_INVALID",
                message="Gmail read authorization is invalid or expired.",
            )
        if response.is_error:
            raise ConnectorUnavailableError(
                code="GMAIL_API_UNAVAILABLE",
                message="Gmail could not return financial messages.",
            )


def _minimize_message(message: _GmailMessage) -> ConnectorEnvelope | None:
    headers = {header.name.casefold(): header.value for header in message.payload.headers}
    subject = normalize_display_text(headers.get("subject", ""))[:MAX_SUBJECT_CHARS]
    sender_name, sender_address = parseaddr(headers.get("from", ""))
    sender_name = normalize_display_text(sender_name)[:160]
    sender_domain = sender_address.rpartition("@")[2].casefold()[:253]
    snippet = normalize_display_text(message.snippet)[:MAX_SNIPPET_CHARS]
    body = _extract_message_text(message.payload)[:MAX_BODY_CHARS]
    relevance_text = " ".join(
        [
            subject.casefold(),
            sender_address.casefold(),
            snippet.casefold(),
            body[:1_000].casefold(),
        ]
    )
    if not any(keyword in relevance_text for keyword in _FINANCIAL_KEYWORDS):
        return None

    tags = ["gmail", "receipt"]
    if any(keyword in relevance_text for keyword in _RECURRING_KEYWORDS):
        tags.append("subscription")
    occurred_at = _message_occurred_at(message, headers.get("date"))
    extraction_text = normalize_display_text(
        "\n".join(part for part in [subject, snippet, body] if part)
    )[:MAX_BODY_CHARS]
    merchant_name = sender_name or sender_domain.split(".", maxsplit=1)[0].replace("-", " ").title()
    return ConnectorEnvelope(
        external_event_id=message.id,
        event_type="gmail_financial_message",
        occurred_at=occurred_at,
        payload={
            "subject": subject,
            "sender_name": merchant_name[:160],
            "sender_domain": sender_domain,
            "extraction_text": extraction_text,
            "tags": tags,
        },
        locator={
            "messageId": message.id,
            "threadId": message.thread_id,
        },
        evidence_excerpt=normalize_display_text(" — ".join([subject, snippet]))[:500],
    )


def _message_occurred_at(
    message: _GmailMessage,
    date_header: str | None,
) -> datetime | None:
    if message.internal_date is not None:
        try:
            return datetime.fromtimestamp(int(message.internal_date) / 1_000, tz=UTC)
        except (OverflowError, ValueError):
            pass
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _extract_message_text(part: _GmailPart) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def visit(current: _GmailPart) -> None:
        if current.body.data:
            decoded = _decode_body(current.body.data)
            if current.mime_type.casefold() == "text/plain":
                plain_parts.append(decoded)
            elif current.mime_type.casefold() == "text/html":
                html_parts.append(_strip_html(decoded))
        for child in current.parts:
            visit(child)

    visit(part)
    selected = plain_parts if plain_parts else html_parts
    return normalize_display_text("\n".join(selected))


def _decode_body(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding)
    except (binascii.Error, ValueError):
        return ""
    return decoded.decode("utf-8", errors="replace")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _strip_html(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return unescape(" ".join(parser.parts))


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None
