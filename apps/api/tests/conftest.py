"""Shared API test fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from importlib import import_module
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import AppEnvironment, Settings
from app.db.base import Base
from app.db.session import Database
from app.factory import create_app

_DATABASE_MARKER = "database"
_RUN_DATABASE_TESTS = "RUN_DATABASE_TESTS"


def _database_tests_enabled() -> bool:
    return os.getenv(_RUN_DATABASE_TESTS) == "1"


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip PostgreSQL integration tests unless the caller explicitly enables them."""
    del config
    if _database_tests_enabled():
        return

    skip_database = pytest.mark.skip(
        reason=f"set {_RUN_DATABASE_TESTS}=1 to run PostgreSQL integration tests",
    )
    for item in items:
        if _DATABASE_MARKER in item.keywords:
            item.add_marker(skip_database)


@pytest.fixture
def test_settings() -> Settings:
    """Use explicit values so tests never depend on a developer's environment."""
    return Settings(
        _env_file=None,
        app_name="SpendGraph Test API",
        app_version="0.1.0-test",
        app_env=AppEnvironment.TEST,
        app_debug=False,
        database_url="postgresql+psycopg://unused:unused@localhost:5432/unused",
        cors_origins='["http://localhost:5173"]',
    )


@pytest.fixture
def api_app(test_settings: Settings) -> FastAPI:
    """Construct an isolated application; no database engine is initialized."""
    return create_app(test_settings)


@pytest.fixture(scope="session")
def database_test_url() -> str:
    """Resolve the explicitly enabled test database from exported environment values."""
    if not _database_tests_enabled():
        pytest.skip(f"set {_RUN_DATABASE_TESTS}=1 to run PostgreSQL integration tests")
    return Settings(_env_file=None).database_url


@pytest.fixture
async def isolated_database(database_test_url: str) -> AsyncIterator[Database]:
    """Create all registered tables inside one disposable PostgreSQL schema."""
    schema_name = f"test_{uuid4().hex}"
    admin_database = Database(database_test_url)
    test_database = Database(
        database_test_url,
        connect_args={"options": f"-csearch_path={schema_name}"},
    )
    schema_created = False

    try:
        async with admin_database.engine().begin() as connection:
            await connection.execute(CreateSchema(schema_name))
        schema_created = True

        # Model modules intentionally register themselves without being imported by
        # app.db.base. Import the aggregate before using declarative metadata.
        import_module("app.models")
        async with test_database.engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        yield test_database
    finally:
        await test_database.dispose()
        try:
            if schema_created:
                async with admin_database.engine().begin() as connection:
                    await connection.execute(DropSchema(schema_name, cascade=True))
        finally:
            await admin_database.dispose()


@pytest.fixture
async def database_api_app(
    api_app: FastAPI,
    isolated_database: Database,
) -> FastAPI:
    """Override the application-owned database with an isolated PostgreSQL database."""
    api_app.state.database = isolated_database
    return api_app
