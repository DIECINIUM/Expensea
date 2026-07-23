"""Operational REST response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.config import AppEnvironment


class HealthResponse(BaseModel):
    """Stable liveness contract used by containers and uptime checks."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    service: str
    version: str
    environment: AppEnvironment
