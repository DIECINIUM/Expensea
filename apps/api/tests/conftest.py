"""Shared API test fixtures."""

import pytest
from fastapi import FastAPI

from app.core.config import AppEnvironment, Settings
from app.factory import create_app


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
