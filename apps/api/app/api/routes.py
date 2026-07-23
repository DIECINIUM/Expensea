"""Operational REST routes.

The health endpoint intentionally reports process health only. Database readiness
belongs in a separate dependency-aware check once the first database-backed phase
is introduced.
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings
from app.schemas.system import HealthResponse

router = APIRouter(tags=["system"])


def settings_from_request(request: Request) -> Settings:
    """Read the application-scoped settings installed by the app factory."""
    return cast(Settings, request.app.state.settings)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Report API process health",
)
async def health(
    settings: Annotated[Settings, Depends(settings_from_request)],
) -> HealthResponse:
    """Return a deterministic liveness response without touching external services."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )
