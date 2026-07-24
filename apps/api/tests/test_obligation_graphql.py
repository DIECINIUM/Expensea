"""GraphQL integration coverage for people and obligation state."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import DEFAULT_DEV_USER_ID
from app.db.session import Database
from app.models import User

CREATE_PERSON = """
  mutation CreatePerson($input: CreatePersonInput!) {
    createPerson(input: $input) {
      __typename
      ... on CreatePersonSuccess { person { id name } }
      ... on ClientProblem { code message field }
    }
  }
"""

CREATE_RECEIVABLE = """
  mutation CreateReceivable($input: CreateReceivableInput!) {
    createReceivable(input: $input) {
      __typename
      ... on CreateReceivableSuccess {
        obligation {
          id personId personName amount currency paidAmount outstandingAmount
          description issuedDate dueDate status
        }
      }
      ... on ClientProblem { code message field }
    }
  }
"""

SETTLE_RECEIVABLE = """
  mutation SettleReceivable($input: SettleReceivableInput!) {
    settleReceivable(input: $input) {
      __typename
      ... on SettleReceivableSuccess {
        settlement { id obligationId amount currency settledAt note }
        obligation { id paidAmount outstandingAmount status }
      }
      ... on ClientProblem { code message field }
    }
  }
"""

OBLIGATION_QUERY = """
  query Obligations {
    obligationSummary {
      currency
      openPayables
      openReceivables
      netExposure
    }
    people { id name }
    receivables {
      id personId personName amount currency paidAmount outstandingAmount
      description issuedDate dueDate status
    }
    payables {
      id personId personName amount currency paidAmount outstandingAmount
      description issuedDate dueDate status
    }
  }
"""


async def _seed_owner(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=DEFAULT_DEV_USER_ID,
                email="obligation-graphql@example.test",
                name="Obligation GraphQL",
                default_currency="INR",
                timezone="UTC",
            )
        )


@pytest.mark.database
@pytest.mark.asyncio
async def test_receivable_graphql_state_and_summary_follow_partial_settlement(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_owner(isolated_database)
    transport = ASGITransport(app=database_api_app)
    today = datetime.now(UTC).date()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        person_response = await client.post(
            "/graphql",
            json={
                "query": CREATE_PERSON,
                "variables": {"input": {"name": " Priya "}},
            },
        )
        person = person_response.json()["data"]["createPerson"]
        person_id = person["person"]["id"]

        receivable_response = await client.post(
            "/graphql",
            json={
                "query": CREATE_RECEIVABLE,
                "variables": {
                    "input": {
                        "personId": person_id,
                        "amount": "2000.0000",
                        "currency": "INR",
                        "description": "Shared trip",
                        "issuedDate": today.isoformat(),
                        "dueDate": (today + timedelta(days=7)).isoformat(),
                    }
                },
            },
        )
        receivable = receivable_response.json()["data"]["createReceivable"]
        obligation_id = receivable["obligation"]["id"]

        settlement_response = await client.post(
            "/graphql",
            json={
                "query": SETTLE_RECEIVABLE,
                "variables": {
                    "input": {
                        "obligationId": obligation_id,
                        "amount": "800.0000",
                        "settledAt": datetime.now(UTC).isoformat(),
                        "note": "First instalment",
                    }
                },
            },
        )
        overpayment_response = await client.post(
            "/graphql",
            json={
                "query": SETTLE_RECEIVABLE,
                "variables": {
                    "input": {
                        "obligationId": obligation_id,
                        "amount": "1200.0001",
                        "settledAt": datetime.now(UTC).isoformat(),
                        "note": None,
                    }
                },
            },
        )
        query_response = await client.post(
            "/graphql",
            json={"query": OBLIGATION_QUERY},
        )

    assert person == {
        "__typename": "CreatePersonSuccess",
        "person": {"id": person_id, "name": "Priya"},
    }
    assert receivable["__typename"] == "CreateReceivableSuccess"
    assert receivable["obligation"]["outstandingAmount"] == "2000.0000"

    settlement = settlement_response.json()["data"]["settleReceivable"]
    assert settlement["__typename"] == "SettleReceivableSuccess"
    assert settlement["settlement"]["amount"] == "800.0000"
    assert settlement["settlement"]["currency"] == "INR"
    assert settlement["obligation"] == {
        "id": obligation_id,
        "paidAmount": "800.0000",
        "outstandingAmount": "1200.0000",
        "status": "PARTIALLY_PAID",
    }
    assert overpayment_response.json()["data"]["settleReceivable"] == {
        "__typename": "ConflictProblem",
        "code": "SETTLEMENT_EXCEEDS_OUTSTANDING",
        "message": "Settlement amount exceeds the outstanding principal.",
        "field": "amount",
    }

    query = query_response.json()["data"]
    assert query["obligationSummary"] == {
        "currency": "INR",
        "openPayables": "0.0000",
        "openReceivables": "1200.0000",
        "netExposure": "1200.0000",
    }
    assert query["people"] == [{"id": person_id, "name": "Priya"}]
    assert query["receivables"][0]["paidAmount"] == "800.0000"
    assert query["receivables"][0]["outstandingAmount"] == "1200.0000"
    assert query["payables"] == []
