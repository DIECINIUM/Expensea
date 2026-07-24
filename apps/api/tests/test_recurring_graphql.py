"""GraphQL integration coverage for recurring-payment workflows."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import DEFAULT_DEV_USER_ID
from app.db.session import Database
from app.models import User

CREATE_RECURRING = """
  mutation CreateRecurring($input: CreateRecurringPaymentInput!) {
    createRecurringPayment(input: $input) {
      __typename
      ... on CreateRecurringPaymentSuccess {
        recurringPayment {
          id
          merchantName
          amount
          currency
          recurrenceRule
          nextExpectedDate
          status
        }
      }
      ... on ClientProblem { code message field }
    }
  }
"""

RECURRING_QUERY = """
  query Recurring {
    recurringSummary(days: 31) {
      currency
      upcomingAmount
      upcomingCount
      windowStart
      windowEnd
    }
    recurringPayments {
      id
      merchantName
      amount
      currency
      recurrenceRule
      nextExpectedDate
      status
    }
  }
"""

RECORD_RECURRING = """
  mutation Record($id: ID!, $expectedDate: Date!, $transactionDate: DateTime!) {
    recordRecurringPayment(
      id: $id
      expectedDate: $expectedDate
      transactionDate: $transactionDate
    ) {
      __typename
      ... on RecordRecurringPaymentSuccess {
        recorded {
          recordedExpectedDate
          transactionId
          transactionDate
          payment { id nextExpectedDate status }
        }
      }
      ... on ClientProblem { code message field }
    }
  }
"""


async def _seed_owner(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=DEFAULT_DEV_USER_ID,
                email="recurring-graphql@example.test",
                name="Recurring GraphQL",
                default_currency="INR",
                timezone="UTC",
            )
        )


@pytest.mark.database
@pytest.mark.asyncio
async def test_recurring_create_summary_and_record_are_one_graphql_contract(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_owner(isolated_database)
    today = datetime.now(UTC).date()
    expected_date = today + timedelta(days=5)
    transport = ASGITransport(app=database_api_app)
    variables = {
        "input": {
            "merchantName": "Netflix",
            "amount": "649.0000",
            "currency": "INR",
            "recurrenceRule": "MONTHLY",
            "nextExpectedDate": expected_date.isoformat(),
        }
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created_response = await client.post(
            "/graphql",
            json={"query": CREATE_RECURRING, "variables": variables},
        )
        summary_response = await client.post(
            "/graphql",
            json={"query": RECURRING_QUERY},
        )

        created = created_response.json()["data"]["createRecurringPayment"]
        payment_id = created["recurringPayment"]["id"]
        record_variables = {
            "id": payment_id,
            "expectedDate": expected_date.isoformat(),
            "transactionDate": datetime.now(UTC).isoformat(),
        }
        recorded_response = await client.post(
            "/graphql",
            json={"query": RECORD_RECURRING, "variables": record_variables},
        )
        duplicate_response = await client.post(
            "/graphql",
            json={"query": RECORD_RECURRING, "variables": record_variables},
        )

    assert created["__typename"] == "CreateRecurringPaymentSuccess"
    assert created["recurringPayment"] == {
        "id": payment_id,
        "merchantName": "Netflix",
        "amount": "649.0000",
        "currency": "INR",
        "recurrenceRule": "MONTHLY",
        "nextExpectedDate": expected_date.isoformat(),
        "status": "ACTIVE",
    }

    summary = summary_response.json()["data"]
    assert summary["recurringSummary"]["upcomingAmount"] == "649.0000"
    assert summary["recurringSummary"]["upcomingCount"] == 1
    assert summary["recurringPayments"] == [created["recurringPayment"]]

    recorded = recorded_response.json()["data"]["recordRecurringPayment"]
    assert recorded["__typename"] == "RecordRecurringPaymentSuccess"
    assert recorded["recorded"]["recordedExpectedDate"] == expected_date.isoformat()
    assert recorded["recorded"]["payment"]["id"] == payment_id
    assert date.fromisoformat(recorded["recorded"]["payment"]["nextExpectedDate"]) > expected_date
    assert duplicate_response.json()["data"]["recordRecurringPayment"] == {
        "__typename": "ConflictProblem",
        "code": "RECURRING_OCCURRENCE_CONFLICT",
        "message": "That expected occurrence is stale or was already recorded.",
        "field": "expectedDate",
    }
