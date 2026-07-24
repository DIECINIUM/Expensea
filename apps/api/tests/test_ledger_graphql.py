"""GraphQL integration coverage for the manual ledger path."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import DEFAULT_DEV_USER_ID, AppEnvironment, Settings
from app.db.session import Database
from app.factory import create_app
from app.models import Category, User

SYSTEM_CATEGORY_ID = UUID("70000000-0000-4000-8000-000000000001")

DASHBOARD_QUERY = """
    query Dashboard {
      me {
        id
        name
        defaultCurrency
        timezone
      }
      financialSummary {
        currency
        periodStart
        periodEnd
        spent
        income
        transactionCount
      }
      spendingByCategory {
        categoryId
        categoryName
        amount
        currency
        sharePercentage
      }
      monthlySpending(months: 2) {
        monthStart
        amount
        currency
      }
      transactions(first: 10) {
        edges {
          cursor
          node {
            id
            amount
            currency
            transactionType
            description
            transactionDate
            status
            merchantName
            categoryName
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
      categories {
        id
        name
      }
    }
"""

CREATE_TRANSACTION_MUTATION = """
    mutation CreateTransaction($input: CreateTransactionInput!) {
      createTransaction(input: $input) {
        __typename
        ... on CreateTransactionSuccess {
          transaction {
            id
            amount
            currency
            transactionType
            description
            transactionDate
            status
            categoryName
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

CREATE_CATEGORY_MUTATION = """
    mutation CreateCategory($input: CreateCategoryInput!) {
      createCategory(input: $input) {
        __typename
        ... on CreateCategorySuccess {
          category {
            id
            name
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


async def _seed_graphql_owner(database: Database) -> None:
    async with database.session_factory()() as session, session.begin():
        session.add(
            User(
                id=DEFAULT_DEV_USER_ID,
                email="graphql-owner@example.test",
                name="GraphQL Owner",
                default_currency="INR",
                timezone="Asia/Kolkata",
            )
        )
        await session.flush()
        session.add(
            Category(
                id=SYSTEM_CATEGORY_ID,
                name="Food",
                normalized_name="food",
            )
        )


@pytest.mark.database
@pytest.mark.asyncio
async def test_manual_mutation_updates_the_subsequent_dashboard_query(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_graphql_owner(isolated_database)
    transport = ASGITransport(app=database_api_app)
    variables = {
        "input": {
            "amount": "420.1250",
            "currency": "INR",
            "transactionType": "EXPENSE",
            "description": "Dinner",
            "transactionDate": datetime.now(UTC).isoformat(),
            "categoryId": str(SYSTEM_CATEGORY_ID),
        }
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        mutation_response = await client.post(
            "/graphql",
            json={"query": CREATE_TRANSACTION_MUTATION, "variables": variables},
        )
        dashboard_response = await client.post(
            "/graphql",
            json={"query": DASHBOARD_QUERY},
        )

    assert mutation_response.status_code == 200
    mutation_payload = mutation_response.json()
    assert "errors" not in mutation_payload
    result = mutation_payload["data"]["createTransaction"]
    assert result["__typename"] == "CreateTransactionSuccess"
    assert result["transaction"] == {
        "id": result["transaction"]["id"],
        "amount": "420.1250",
        "currency": "INR",
        "transactionType": "EXPENSE",
        "description": "Dinner",
        "transactionDate": result["transaction"]["transactionDate"],
        "status": "POSTED",
        "categoryName": "Food",
    }

    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert "errors" not in dashboard
    data = dashboard["data"]
    assert data["me"]["id"] == str(DEFAULT_DEV_USER_ID)
    assert data["me"]["name"] == "GraphQL Owner"
    assert data["financialSummary"]["spent"] == "420.1250"
    assert data["financialSummary"]["transactionCount"] == 1
    assert data["spendingByCategory"] == [
        {
            "categoryId": str(SYSTEM_CATEGORY_ID),
            "categoryName": "Food",
            "amount": "420.1250",
            "currency": "INR",
            "sharePercentage": 100,
        }
    ]
    assert data["transactions"]["edges"][0]["node"]["amount"] == "420.1250"
    assert data["transactions"]["pageInfo"]["hasNextPage"] is False
    assert data["categories"] == [{"id": str(SYSTEM_CATEGORY_ID), "name": "Food"}]


@pytest.mark.database
@pytest.mark.asyncio
async def test_create_transaction_returns_typed_validation_problem(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_graphql_owner(isolated_database)
    transport = ASGITransport(app=database_api_app)
    variables = {
        "input": {
            "amount": "1.00001",
            "currency": "INR",
            "transactionType": "EXPENSE",
            "description": "Invalid precision",
            "transactionDate": datetime.now(UTC).isoformat(),
        }
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/graphql",
            json={"query": CREATE_TRANSACTION_MUTATION, "variables": variables},
        )

    payload = response.json()
    assert "errors" not in payload
    assert payload["data"]["createTransaction"] == {
        "__typename": "ValidationProblem",
        "code": "INVALID_AMOUNT",
        "message": "Amount must be positive, finite, and have at most four decimal places.",
        "field": "amount",
    }


@pytest.mark.database
@pytest.mark.asyncio
async def test_create_category_returns_success_then_typed_conflict(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    await _seed_graphql_owner(isolated_database)
    transport = ASGITransport(app=database_api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/graphql",
            json={
                "query": CREATE_CATEGORY_MUTATION,
                "variables": {"input": {"name": "Work travel"}},
            },
        )
        duplicate = await client.post(
            "/graphql",
            json={
                "query": CREATE_CATEGORY_MUTATION,
                "variables": {"input": {"name": " work   travel "}},
            },
        )

    created_result = created.json()["data"]["createCategory"]
    assert created_result["__typename"] == "CreateCategorySuccess"
    assert created_result["category"]["name"] == "Work travel"
    assert duplicate.json()["data"]["createCategory"] == {
        "__typename": "ConflictProblem",
        "code": "CATEGORY_ALREADY_EXISTS",
        "message": "A category with that name already exists.",
        "field": "name",
    }


@pytest.mark.asyncio
async def test_finance_query_requires_identity_when_development_auth_is_disabled() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        app_debug=False,
        dev_auth_enabled=False,
        database_url="postgresql+psycopg://unused:unused@localhost:5432/unused",
        cors_origins='["http://localhost:5173"]',
    )
    application = create_app(settings)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/graphql", json={"query": "{ me { id } }"})

    payload = response.json()
    assert payload["data"] is None
    assert payload["errors"][0]["message"] == "Authentication is required."
    assert payload["errors"][0]["extensions"]["code"] == "UNAUTHENTICATED"
