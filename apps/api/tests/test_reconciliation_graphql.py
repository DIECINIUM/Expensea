"""GraphQL integration coverage for owner-facing duplicate review."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.connectors.contracts import ConnectorEnvelope
from app.connectors.mock_receipt import MockReceiptConnector
from app.core.config import DEFAULT_DEV_USER_ID
from app.db.session import Database
from app.ingestion.service import IngestionService
from app.models import User

SOURCE_TIME = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)

CASE_FIELDS = """
    id
    normalizedEventId
    source
    eventKind
    amount
    currency
    description
    occurredAt
    merchantName
    candidateTransactionId
    candidateDescription
    candidateOccurredAt
    candidateMerchantName
    resultingTransactionId
    initialDecision
    status
    score
    scoreVersion
    reasons
    createdAt
    updatedAt
    canUnmerge
    actions {
      id
      actionType
      fromTransactionId
      toTransactionId
      score
      reasons
      createdAt
    }
"""

CASES_QUERY = (
    """
    query ReconciliationCases($status: ReconciliationStatusValue) {
      reconciliationCases(status: $status) {
    """
    + CASE_FIELDS
    + """
      }
    }
"""
)

MERGE_CASE = (
    """
    mutation MergeCase($id: ID!) {
      mergeReconciliationCase(id: $id) {
        __typename
        ... on ReviewReconciliationCaseSuccess {
          case {
    """
    + CASE_FIELDS
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

UNMERGE_CASE = (
    """
    mutation UnmergeCase($id: ID!) {
      unmergeReconciliationCase(id: $id) {
        __typename
        ... on ReviewReconciliationCaseSuccess {
          case {
    """
    + CASE_FIELDS
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

KEEP_SEPARATE = (
    """
    mutation KeepSeparate($id: ID!) {
      keepReconciliationCaseSeparate(id: $id) {
        __typename
        ... on ReviewReconciliationCaseSuccess {
          case {
    """
    + CASE_FIELDS
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


async def _seed_owner(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=DEFAULT_DEV_USER_ID,
                email="reconciliation-graphql@example.test",
                name="Reconciliation GraphQL",
                default_currency="INR",
                timezone="Asia/Kolkata",
            )
        )


def _receipt(external_event_id: str, description: str) -> ConnectorEnvelope:
    return ConnectorEnvelope(
        external_event_id=external_event_id,
        event_type="receipt",
        occurred_at=SOURCE_TIME,
        payload={
            "event_kind": "expense",
            "amount": "480.0000",
            "currency": "INR",
            "description": description,
            "merchant_name": "Swiggy",
            "confidence": "1.0000",
        },
        locator={"messageId": external_event_id},
        evidence_excerpt="Swiggy receipt for INR 480",
    )


async def _create_pending_case(database: Database) -> None:
    ingestion = IngestionService(database)
    connector = MockReceiptConnector(())
    await ingestion.ingest_envelope(
        DEFAULT_DEV_USER_ID,
        connector,
        _receipt("graphql-receipt-1", "Swiggy dinner order"),
    )
    await ingestion.ingest_envelope(
        DEFAULT_DEV_USER_ID,
        connector,
        _receipt("graphql-receipt-2", "Card purchase").model_copy(
            update={"occurred_at": SOURCE_TIME + timedelta(minutes=1)}
        ),
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_graphql_can_merge_then_unmerge_an_explained_case(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_owner(isolated_database)
    await _create_pending_case(isolated_database)
    transport = ASGITransport(app=database_api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        queued = await client.post(
            "/graphql",
            json={"query": CASES_QUERY, "variables": {"status": "PENDING"}},
        )
        queued_payload = queued.json()
        case = queued_payload["data"]["reconciliationCases"][0]
        merged = await client.post(
            "/graphql",
            json={"query": MERGE_CASE, "variables": {"id": case["id"]}},
        )
        unmerged = await client.post(
            "/graphql",
            json={"query": UNMERGE_CASE, "variables": {"id": case["id"]}},
        )

    assert "errors" not in queued_payload
    assert case["source"] == "MOCK_RECEIPT"
    assert case["initialDecision"] == "POSSIBLE_DUPLICATE"
    assert case["status"] == "PENDING"
    assert case["candidateTransactionId"] is not None
    assert case["resultingTransactionId"] is None
    assert case["scoreVersion"] == "reconciliation-score/v1"
    assert case["reasons"][-1] == "SCORE_POSSIBLE_DUPLICATE"
    assert case["actions"][0]["actionType"] == "CANDIDATE_FLAGGED"

    merged_payload = merged.json()
    assert "errors" not in merged_payload
    merged_case = merged_payload["data"]["mergeReconciliationCase"]["case"]
    assert merged_case["status"] == "MERGED"
    assert merged_case["canUnmerge"] is True
    assert merged_case["actions"][-1]["actionType"] == "USER_MERGED"

    unmerged_payload = unmerged.json()
    assert "errors" not in unmerged_payload
    unmerged_case = unmerged_payload["data"]["unmergeReconciliationCase"]["case"]
    assert unmerged_case["status"] == "UNMERGED"
    assert unmerged_case["canUnmerge"] is False
    assert unmerged_case["resultingTransactionId"] != unmerged_case["candidateTransactionId"]
    assert unmerged_case["actions"][-1]["actionType"] == "USER_UNMERGED"


@pytest.mark.database
@pytest.mark.asyncio
async def test_graphql_returns_typed_validation_not_found_and_conflict_problems(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_owner(isolated_database)
    await _create_pending_case(isolated_database)
    transport = ASGITransport(app=database_api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        queue = await client.post(
            "/graphql",
            json={"query": CASES_QUERY, "variables": {"status": "PENDING"}},
        )
        case_id = queue.json()["data"]["reconciliationCases"][0]["id"]
        invalid = await client.post(
            "/graphql",
            json={"query": MERGE_CASE, "variables": {"id": "not-a-uuid"}},
        )
        missing = await client.post(
            "/graphql",
            json={
                "query": MERGE_CASE,
                "variables": {"id": "ffffffff-ffff-4fff-8fff-ffffffffffff"},
            },
        )
        resolved = await client.post(
            "/graphql",
            json={"query": KEEP_SEPARATE, "variables": {"id": case_id}},
        )
        stale = await client.post(
            "/graphql",
            json={"query": MERGE_CASE, "variables": {"id": case_id}},
        )

    assert invalid.json()["data"]["mergeReconciliationCase"] == {
        "__typename": "ValidationProblem",
        "code": "INVALID_ID",
        "message": "ID must be a UUID.",
        "field": "id",
    }
    assert missing.json()["data"]["mergeReconciliationCase"]["__typename"] == "NotFoundProblem"
    assert (
        missing.json()["data"]["mergeReconciliationCase"]["code"] == "RECONCILIATION_CASE_NOT_FOUND"
    )
    assert (
        resolved.json()["data"]["keepReconciliationCaseSeparate"]["case"]["status"]
        == "KEPT_SEPARATE"
    )
    assert stale.json()["data"]["mergeReconciliationCase"]["__typename"] == "ConflictProblem"
    assert (
        stale.json()["data"]["mergeReconciliationCase"]["code"]
        == "RECONCILIATION_CASE_ALREADY_RESOLVED"
    )
