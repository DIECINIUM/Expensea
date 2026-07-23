"""PostgreSQL integration-fixture contract."""

import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.db.session import Database


@pytest.mark.database
@pytest.mark.asyncio
async def test_isolated_database_uses_a_disposable_schema(
    isolated_database: Database,
    database_api_app: FastAPI,
) -> None:
    async with isolated_database.session_factory()() as session:
        schema_name = await session.scalar(text("SELECT current_schema()"))
        users_table = await session.scalar(text("SELECT to_regclass('users')::text"))

    assert isinstance(schema_name, str)
    assert schema_name.startswith("test_")
    assert users_table == "users"
    assert database_api_app.state.database is isolated_database
