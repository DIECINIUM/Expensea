"""Independently validated API admission and worker limits."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class JobsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    concurrency: int = Field(default=4, ge=1, le=16)
    max_pending: int = Field(default=1000, ge=1, le=10000)
    max_pending_per_owner: int = Field(default=50, ge=1, le=1000)
    max_attempts: int = Field(default=3, ge=1, le=5)
    lease_seconds: int = Field(default=180, ge=10, le=1800)
    timeout_seconds: int = Field(default=120, ge=1, le=1200)
    poll_seconds: float = Field(default=1, ge=0.1, le=30)
    backoff_seconds: float = Field(default=2, ge=0.1, le=60)
    max_backoff_seconds: float = Field(default=300, ge=1, le=3600)

    @model_validator(mode="after")
    def lease_exceeds_timeout(self) -> "JobsSettings":
        if self.lease_seconds <= self.timeout_seconds + 5:
            raise ValueError("lease_seconds must exceed timeout_seconds by more than five seconds")
        if self.max_backoff_seconds < self.backoff_seconds:
            raise ValueError("max_backoff_seconds must not be smaller than backoff_seconds")
        return self
