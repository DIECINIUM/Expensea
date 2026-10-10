"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agent.router import create_agent_router
from app.agent.service import FinanceAgentService
from app.ai.factory import create_structured_provider
from app.analytics.service import AnalyticsService
from app.api.routes import router as system_router
from app.auth.router import router as auth_router
from app.auth.session import OAuthAccessLogFilter, authenticate_request
from app.connections.router import router as connections_router
from app.core.config import Settings, get_settings
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.observability import (
    ObservedProvider,
    OperationalTelemetry,
    TelemetryMiddleware,
)
from app.core.observability import (
    router as operations_router,
)
from app.db.session import Database
from app.graphql.router import create_graphql_router
from app.jobs.config import JobsSettings
from app.jobs.routes import router as jobs_router
from app.ledger.obligation_service import ObligationService
from app.ledger.recurring_service import RecurringPaymentService
from app.ledger.service import LedgerService


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Release only the database resources owned by this application."""
    yield
    database = cast(Database, application.state.database)
    await database.dispose()
    await application.state.oauth_http_client.aclose()
    application.state.telemetry.shutdown()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application with explicit, test-friendly dependencies."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level.value)
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, OAuthAccessLogFilter) for item in access_logger.filters):
        access_logger.addFilter(OAuthAccessLogFilter())

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        debug=app_settings.debug,
        docs_url="/docs" if app_settings.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.database = Database(app_settings.database_url)
    telemetry = OperationalTelemetry.from_environment()
    application.state.telemetry = telemetry
    application.state.structured_provider = ObservedProvider(
        create_structured_provider(app_settings), telemetry
    )
    application.state.jobs_settings = JobsSettings()
    application.state.oauth_http_client = httpx.AsyncClient(timeout=30, follow_redirects=False)

    # The request context turns unexpected exceptions into non-sensitive,
    # correlation-friendly responses. CORS is added last so it wraps those errors.
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(TelemetryMiddleware, telemetry=telemetry)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID"],
    )

    application.include_router(system_router)
    application.include_router(auth_router)
    application.include_router(connections_router)
    application.include_router(operations_router)
    application.include_router(jobs_router)

    def resolve_agent(request: Request) -> FinanceAgentService:
        database = cast(Database, request.app.state.database)
        cached_database = getattr(request.app.state, "agent_database", None)
        if cached_database is not database:
            request.app.state.finance_agent = FinanceAgentService(
                LedgerService(database),
                AnalyticsService(database),
                ObligationService(database),
                RecurringPaymentService(database),
                provider=request.app.state.structured_provider,
            )
            request.app.state.agent_database = database
        return cast(FinanceAgentService, request.app.state.finance_agent)

    application.include_router(
        create_agent_router(
            resolve_agent,
            authenticate_request,
            allowed_origins=tuple(app_settings.cors_origin_list),
        )
    )
    application.include_router(
        create_graphql_router(app_settings),
        prefix="/graphql",
    )
    return application
