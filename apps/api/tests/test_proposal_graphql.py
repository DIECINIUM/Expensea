"""GraphQL integration coverage for note submission and proposal review."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.ai.mock import MockStructuredProvider
from app.core.config import DEFAULT_DEV_USER_ID
from app.db.session import Database
from app.models import User

REQUEST_ID = UUID("d1000000-0000-4000-8000-000000000001")

PROPOSAL_FIELDS = """
    id
    rawEventId
    source
    eventKind
    amount
    currency
    description
    occurredAt
    dueDate
    merchantName
    counterparty
    recurrenceRule
    nextExpectedDate
    categoryHint
    tags
    confidence
    status
    reviewReasons
    provider
    model
    promptVersion
    canonicalTargetType
    canonicalTargetId
"""

SUBMIT_NOTE = (
    """
    mutation Submit($input: SubmitFinancialNoteInput!) {
      submitFinancialNote(input: $input) {
        __typename
        ... on SubmitFinancialNoteSuccess {
          proposal {
    """
    + PROPOSAL_FIELDS
    + """
          }
        }
        ... on ClientProblem {
          code
          message
          field
        }
      }
    }
"""
)

REVIEW_PROPOSAL = (
    """
    mutation Review($id: ID!) {
      approveFinancialProposal(id: $id) {
        __typename
        ... on ReviewFinancialProposalSuccess {
          proposal {
    """
    + PROPOSAL_FIELDS
    + """
          }
        }
        ... on ClientProblem {
          code
          message
          field
        }
      }
    }
"""
)

PROPOSAL_QUEUE = (
    """
    query Queue($status: ProposalStatusValue) {
      financialEventProposals(status: $status) {
    """
    + PROPOSAL_FIELDS
    + """
      }
    }
"""
)


async def _seed_owner(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=DEFAULT_DEV_USER_ID,
                email="proposal-graphql@example.test",
                name="Proposal GraphQL",
                default_currency="INR",
                timezone="Asia/Kolkata",
            )
        )


@pytest.mark.database
@pytest.mark.asyncio
async def test_graphql_note_review_updates_queue_and_canonical_target(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_owner(isolated_database)
    database_api_app.state.structured_provider = MockStructuredProvider(
        [
            {
                "event_kind": "expense",
                "amount": "249.0000",
                "currency": "INR",
                "description": "Music subscription",
                "occurred_at": "2026-07-24T10:00:00+05:30",
                "merchant_name": "Example Music",
                "category_hint": "Entertainment",
                "tags": ["subscription", "music"],
                "confidence": "0.9300",
            }
        ]
    )
    transport = ASGITransport(app=database_api_app)
    variables = {
        "input": {
            "note": "Paid ₹249 for music subscription today",
            "sourceTimestamp": datetime(2026, 7, 24, 4, 30, tzinfo=UTC).isoformat(),
            "clientRequestId": str(REQUEST_ID),
            "labels": ["Personal"],
        }
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        submitted = await client.post(
            "/graphql",
            json={"query": SUBMIT_NOTE, "variables": variables},
        )
        pending = await client.post(
            "/graphql",
            json={"query": PROPOSAL_QUEUE, "variables": {"status": "NEEDS_REVIEW"}},
        )
        proposal_id = submitted.json()["data"]["submitFinancialNote"]["proposal"]["id"]
        approved = await client.post(
            "/graphql",
            json={
                "query": REVIEW_PROPOSAL,
                "variables": {"id": proposal_id},
            },
        )
        empty_queue = await client.post(
            "/graphql",
            json={"query": PROPOSAL_QUEUE, "variables": {"status": "NEEDS_REVIEW"}},
        )
        reviewed = await client.post(
            "/graphql",
            json={"query": PROPOSAL_QUEUE, "variables": {"status": "APPROVED"}},
        )

    submit_payload = submitted.json()
    assert "errors" not in submit_payload
    proposal = submit_payload["data"]["submitFinancialNote"]["proposal"]
    assert submit_payload["data"]["submitFinancialNote"]["__typename"] == (
        "SubmitFinancialNoteSuccess"
    )
    assert proposal["source"] == "MANUAL_NOTE"
    assert proposal["eventKind"] == "EXPENSE"
    assert proposal["amount"] == "249.0000"
    assert proposal["status"] == "NEEDS_REVIEW"
    assert proposal["tags"] == ["subscription", "music"]
    assert proposal["canonicalTargetId"] is None
    assert pending.json()["data"]["financialEventProposals"] == [proposal]

    approved_proposal = approved.json()["data"]["approveFinancialProposal"]["proposal"]
    assert approved_proposal["status"] == "APPROVED"
    assert approved_proposal["canonicalTargetType"] == "transaction"
    assert approved_proposal["canonicalTargetId"] is not None
    assert empty_queue.json()["data"]["financialEventProposals"] == []
    assert reviewed.json()["data"]["financialEventProposals"] == [approved_proposal]


@pytest.mark.database
@pytest.mark.asyncio
async def test_graphql_disabled_provider_returns_typed_problem_and_retains_raw_note(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_owner(isolated_database)
    transport = ASGITransport(app=database_api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/graphql",
            json={
                "query": SUBMIT_NOTE,
                "variables": {
                    "input": {
                        "note": "Paid ₹10 for tea",
                        "sourceTimestamp": datetime.now(UTC).isoformat(),
                        "clientRequestId": str(REQUEST_ID),
                    }
                },
            },
        )

    payload = response.json()
    assert "errors" not in payload
    assert payload["data"]["submitFinancialNote"] == {
        "__typename": "ValidationProblem",
        "code": "AI_PROVIDER_DISABLED",
        "message": "Structured AI extraction is disabled.",
        "field": None,
    }
