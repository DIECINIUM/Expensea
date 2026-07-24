"""Environment-backed application settings."""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from typing import Any, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class AppEnvironment(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Log levels accepted from the environment."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AIProvider(StrEnum):
    """Supported server-side structured completion providers."""

    DISABLED = "disabled"
    OLLAMA = "ollama"


DEFAULT_DEV_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


class Settings(BaseSettings):
    """Runtime configuration.

    Field names intentionally mirror their uppercase environment variables. For
    example, ``app_debug`` reads ``APP_DEBUG`` and ``database_url`` reads
    ``DATABASE_URL``. ``CORS_ORIGINS`` accepts either a JSON string array or a
    comma-separated list.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    app_name: str = "SpendGraph AI API"
    app_version: str = "0.1.0"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_debug: bool = False
    log_level: LogLevel = LogLevel.INFO

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = '["http://localhost:5173"]'

    dev_auth_enabled: bool = True
    dev_user_id: UUID = DEFAULT_DEV_USER_ID

    ai_provider: AIProvider = AIProvider.DISABLED
    ai_base_url: str = "http://127.0.0.1:11434"
    ai_model: str = Field(default="gemma4:e4b", min_length=1, max_length=120)
    ai_request_timeout_seconds: float = Field(default=120.0, ge=1, le=300)
    ai_max_input_chars: int = Field(default=8_000, ge=256, le=32_000)
    ai_review_confidence_threshold: float = Field(default=0.85, ge=0, le=1)

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = "spendgraph"
    postgres_password: str = Field(default="spendgraph", min_length=1, repr=False)
    postgres_db: str = "spendgraph"
    database_url: str = Field(
        default="",
        min_length=1,
        repr=False,
    )

    @model_validator(mode="before")
    @classmethod
    def assemble_database_url(cls, raw_values: Any) -> Any:
        """Build one safely encoded DSN from PostgreSQL parts when no override exists."""
        if not isinstance(raw_values, dict):
            return raw_values

        values = dict(raw_values)
        if values.get("database_url"):
            return values

        values["database_url"] = URL.create(
            "postgresql+psycopg",
            username=str(values.get("postgres_user", "spendgraph")),
            password=str(values.get("postgres_password", "spendgraph")),
            host=str(values.get("postgres_host", "localhost")),
            port=int(values.get("postgres_port", 5432)),
            database=str(values.get("postgres_db", "spendgraph")),
        ).render_as_string(hide_password=False)
        return values

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: Any) -> Any:
        """Allow conventional lowercase/mixed-case log-level values."""
        return value.upper() if isinstance(value, str) else value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Fail before startup when the configured async PostgreSQL URL is unusable."""
        try:
            url = make_url(value)
        except ArgumentError as exc:
            msg = "DATABASE_URL must be a valid SQLAlchemy URL"
            raise ValueError(msg) from exc

        if url.drivername != "postgresql+psycopg":
            msg = "DATABASE_URL must use the postgresql+psycopg driver"
            raise ValueError(msg)
        if not url.host or not url.database:
            msg = "DATABASE_URL must include a host and database name"
            raise ValueError(msg)
        return value

    @field_validator("ai_base_url")
    @classmethod
    def validate_ai_base_url(cls, value: str) -> str:
        """Accept one exact HTTP(S) provider origin without embedded credentials."""
        normalized = value.strip().rstrip("/")
        parts = urlsplit(normalized)
        is_provider_origin = (
            parts.scheme in {"http", "https"}
            and parts.hostname is not None
            and parts.username is None
            and parts.password is None
            and parts.path in {"", "/"}
            and not parts.query
            and not parts.fragment
        )
        if not is_provider_origin:
            msg = "AI_BASE_URL must be an exact HTTP(S) origin without credentials or paths"
            raise ValueError(msg)
        return normalized

    @field_validator("ai_model")
    @classmethod
    def normalize_ai_model(cls, value: str) -> str:
        """Reject whitespace-only or padded provider model identifiers."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("AI_MODEL cannot be blank")
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        """Validate exact HTTP(S) origins and reject credential-unsafe wildcards."""
        _parse_cors_origins(value)
        return value

    @model_validator(mode="after")
    def validate_environment_policy(self) -> Self:
        """Reject debug in deployed tiers and development defaults in production."""
        if self.app_env in {AppEnvironment.STAGING, AppEnvironment.PRODUCTION} and self.app_debug:
            msg = "APP_DEBUG must be false in staging and production"
            raise ValueError(msg)

        if self.app_env is AppEnvironment.PRODUCTION:
            database = make_url(self.database_url)
            if database.host in {"localhost", "127.0.0.1", "::1"}:
                msg = "Production database configuration cannot target localhost"
                raise ValueError(msg)
            if database.password == "spendgraph":
                msg = "Production database configuration cannot use the development password"
                raise ValueError(msg)
            if not self.cors_origin_list:
                msg = "Production requires at least one explicit CORS origin"
                raise ValueError(msg)

            for origin in self.cors_origin_list:
                hostname = urlsplit(origin).hostname
                if hostname in {"localhost", "127.0.0.1", "::1"}:
                    msg = "Production CORS_ORIGINS cannot target localhost"
                    raise ValueError(msg)

        if (
            self.app_env in {AppEnvironment.STAGING, AppEnvironment.PRODUCTION}
            and self.dev_auth_enabled
        ):
            msg = "DEV_AUTH_ENABLED must be false in staging and production"
            raise ValueError(msg)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """Normalize supported CORS env syntax to Starlette's list form."""
        return _parse_cors_origins(self.cors_origins)

    @property
    def debug(self) -> bool:
        """Expose the conventional framework-facing name for ``APP_DEBUG``."""
        return self.app_debug


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the immutable-by-convention process settings singleton."""
    return Settings()


def _parse_cors_origins(raw_value: str) -> list[str]:
    """Parse and validate JSON-array or comma-separated CORS configuration."""
    normalized_value = raw_value.strip()
    if not normalized_value:
        return []

    if normalized_value.startswith("["):
        try:
            parsed = json.loads(normalized_value)
        except json.JSONDecodeError as exc:
            msg = "CORS_ORIGINS must be valid JSON or a comma-separated list"
            raise ValueError(msg) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            msg = "CORS_ORIGINS must be a JSON array of strings"
            raise ValueError(msg)
        candidates = parsed
    else:
        candidates = normalized_value.split(",")

    origins: list[str] = []
    for candidate in candidates:
        origin = candidate.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            msg = "CORS_ORIGINS cannot contain '*' when credentials are enabled"
            raise ValueError(msg)

        parts = urlsplit(origin)
        is_exact_origin = (
            parts.scheme in {"http", "https"}
            and parts.hostname is not None
            and parts.username is None
            and parts.password is None
            and parts.path in {"", "/"}
            and not parts.query
            and not parts.fragment
        )
        if not is_exact_origin:
            msg = "Each CORS origin must be an exact HTTP(S) origin without credentials or paths"
            raise ValueError(msg)
        origins.append(origin)

    return origins
