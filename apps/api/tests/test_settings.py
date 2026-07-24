"""Configuration parsing tests."""

from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import DEFAULT_DEV_USER_ID, AIProvider, AppEnvironment, Settings


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (
            '["http://localhost:5173", "https://app.example.com/"]',
            [
                "http://localhost:5173",
                "https://app.example.com",
            ],
        ),
        (
            "http://localhost:5173, https://app.example.com/",
            [
                "http://localhost:5173",
                "https://app.example.com",
            ],
        ),
        ("", []),
    ],
)
def test_cors_origins_accept_json_or_csv(raw_value: str, expected: list[str]) -> None:
    settings = Settings(_env_file=None, cors_origins=raw_value)

    assert settings.cors_origin_list == expected


def test_cors_origins_reject_non_string_json_values() -> None:
    with pytest.raises(ValueError, match="JSON array of strings"):
        Settings(_env_file=None, cors_origins='["https://app.example.com", 42]')


@pytest.mark.parametrize(
    "base_url",
    [
        "10.0.0.5:11434",
        "ftp://models.example.test",
        "http://user:secret@models.example.test",
        "https://models.example.test/api",
        "https://models.example.test?token=secret",
    ],
)
def test_ai_base_url_rejects_inexact_or_credentialed_values(base_url: str) -> None:
    with pytest.raises(ValidationError, match="AI_BASE_URL"):
        Settings(_env_file=None, ai_base_url=base_url)


def test_ollama_settings_are_server_only_and_typed() -> None:
    settings = Settings(
        _env_file=None,
        ai_provider="ollama",
        ai_base_url="http://10.0.0.5:11434/",
        ai_model=" gemma4:e4b ",
        ai_request_timeout_seconds=90,
        ai_review_confidence_threshold=0.9,
    )

    assert settings.ai_provider is AIProvider.OLLAMA
    assert settings.ai_base_url == "http://10.0.0.5:11434"
    assert settings.ai_model == "gemma4:e4b"
    assert settings.ai_request_timeout_seconds == 90
    assert settings.ai_review_confidence_threshold == 0.9


@pytest.mark.parametrize(
    "raw_value",
    [
        "[",
        "*",
        "localhost:5173",
        "https://user:secret@app.example.com",
        "https://app.example.com/path",
        "https://app.example.com?query=value",
    ],
)
def test_cors_origins_reject_unsafe_or_inexact_values(raw_value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=raw_value)


@pytest.mark.parametrize(
    "database_url",
    [
        "not-a-url",
        "sqlite:///spendgraph.db",
        "postgresql://user:secret@db.example.com/spendgraph",
        "postgresql+psycopg:///spendgraph",
    ],
)
def test_database_url_requires_async_psycopg_postgresql(database_url: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=None, database_url=database_url)


@pytest.mark.parametrize(
    "environment",
    [AppEnvironment.STAGING, AppEnvironment.PRODUCTION],
)
def test_deployed_environments_reject_debug(environment: AppEnvironment) -> None:
    with pytest.raises(ValidationError, match="APP_DEBUG"):
        Settings(
            _env_file=None,
            app_env=environment,
            app_debug=True,
        )


def test_production_rejects_implicit_development_defaults() -> None:
    with pytest.raises(ValidationError, match="cannot target localhost"):
        Settings(
            _env_file=None,
            app_env=AppEnvironment.PRODUCTION,
            app_debug=False,
        )


def test_production_requires_non_local_cors_origin() -> None:
    with pytest.raises(ValidationError, match="cannot target localhost"):
        Settings(
            _env_file=None,
            app_env=AppEnvironment.PRODUCTION,
            database_url="postgresql+psycopg://app:secret@db.example.com/spendgraph",
            cors_origins='["http://localhost:5173"]',
        )


def test_valid_production_settings_hide_database_credentials_from_repr() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.PRODUCTION,
        dev_auth_enabled=False,
        database_url="postgresql+psycopg://app:top-secret@db.example.com/spendgraph",
        cors_origins='["https://app.example.com"]',
    )

    assert settings.cors_origin_list == ["https://app.example.com"]
    assert "top-secret" not in repr(settings)


def test_development_auth_uses_a_fixed_server_configured_user_id() -> None:
    configured_user_id = UUID("b950035c-8e59-455a-a71f-70f3bafc32e9")

    settings = Settings(
        _env_file=None,
        dev_user_id=configured_user_id,
    )

    assert settings.dev_auth_enabled is True
    assert settings.dev_user_id == configured_user_id
    assert Settings(_env_file=None).dev_user_id == DEFAULT_DEV_USER_ID


@pytest.mark.parametrize(
    "environment",
    [AppEnvironment.STAGING, AppEnvironment.PRODUCTION],
)
def test_deployed_environments_reject_development_auth(
    environment: AppEnvironment,
) -> None:
    with pytest.raises(ValidationError, match="DEV_AUTH_ENABLED"):
        Settings(
            _env_file=None,
            app_env=environment,
            app_debug=False,
            database_url="postgresql+psycopg://app:secret@db.example.com/spendgraph",
            cors_origins='["https://app.example.com"]',
        )


def test_deployed_environment_can_disable_development_auth() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.STAGING,
        app_debug=False,
        dev_auth_enabled=False,
    )

    assert settings.dev_auth_enabled is False


def test_database_url_is_safely_derived_from_postgres_components() -> None:
    settings = Settings(
        _env_file=None,
        postgres_host="127.0.0.1",
        postgres_port=5544,
        postgres_user="local-user",
        postgres_password="p@ss:/word",
        postgres_db="local-db",
    )

    database = make_url(settings.database_url)
    assert database.drivername == "postgresql+psycopg"
    assert database.host == "127.0.0.1"
    assert database.port == 5544
    assert database.username == "local-user"
    assert database.password == "p@ss:/word"
    assert database.database == "local-db"


def test_app_debug_uses_namespaced_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG", "release")
    monkeypatch.setenv("APP_DEBUG", "true")

    settings = Settings(_env_file=None)

    assert settings.debug is True
