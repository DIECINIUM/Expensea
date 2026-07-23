"""Database-free checks for both API transports."""

import logging
import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.db.session import Database


@pytest.mark.asyncio
async def test_health_contract_and_request_id(api_app: FastAPI) -> None:
    request_id = "test-request-123"
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == {
        "status": "ok",
        "service": "SpendGraph Test API",
        "version": "0.1.0-test",
        "environment": "test",
    }


@pytest.mark.asyncio
async def test_invalid_request_id_is_replaced(api_app: FastAPI) -> None:
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "not valid!"})

    generated_request_id = response.headers["X-Request-ID"]
    assert generated_request_id != "not valid!"
    assert re.fullmatch(r"[0-9a-f]{32}", generated_request_id)


@pytest.mark.asyncio
async def test_graphql_health_and_app_info(api_app: FastAPI) -> None:
    transport = ASGITransport(app=api_app)
    query = """
        query FoundationHealth {
          health
          appInfo {
            name
            version
            environment
          }
        }
    """

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/graphql", json={"query": query})

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "health": "ok",
            "appInfo": {
                "name": "SpendGraph Test API",
                "version": "0.1.0-test",
                "environment": "test",
            },
        }
    }


@pytest.mark.asyncio
async def test_graphql_queries_are_not_accepted_via_get(api_app: FastAPI) -> None:
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/graphql", params={"query": "{ health }"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cors_preflight_for_configured_web_origin(api_app: FastAPI) -> None:
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/graphql",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.asyncio
async def test_unhandled_error_is_generic_correlated_and_cors_enabled(
    api_app: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fail() -> None:
        msg = "sensitive internal detail"
        raise RuntimeError(msg)

    api_app.add_api_route("/fail-for-test", fail)
    transport = ASGITransport(app=api_app, raise_app_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="app.request"):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/fail-for-test",
                headers={"Origin": "http://localhost:5173"},
            )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "sensitive internal detail" not in response.text
    assert "sensitive internal detail" not in caplog.text
    assert any(getattr(record, "error_type", None) == "RuntimeError" for record in caplog.records)


def test_app_owns_database_from_explicit_settings(api_app: FastAPI) -> None:
    database = api_app.state.database

    assert isinstance(database, Database)
    assert database.database_url == ("postgresql+psycopg://unused:unused@localhost:5432/unused")
    assert database.engine().sync_engine.hide_parameters is True


def test_uvicorn_access_log_is_disabled_in_favor_of_path_only_events(
    api_app: FastAPI,
) -> None:
    del api_app  # App construction applies the logging policy.
    access_logger = logging.getLogger("uvicorn.access")

    assert access_logger.handlers == []
    assert access_logger.propagate is False
    assert access_logger.level == logging.WARNING
