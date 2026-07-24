"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.factory import create_structured_provider
from app.api.routes import router as system_router
from app.core.config import Settings, get_settings
from app.core.logging import RequestContextMiddleware, configure_logging
from app.db.session import Database
from app.graphql.router import create_graphql_router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Release only the database resources owned by this application."""
    yield
    database = cast(Database, application.state.database)
    await database.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application with explicit, test-friendly dependencies."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level.value)

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
    application.state.structured_provider = create_structured_provider(app_settings)

    # The request context turns unexpected exceptions into non-sensitive,
    # correlation-friendly responses. CORS is added last so it wraps those errors.
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    application.include_router(system_router)
    application.include_router(
        create_graphql_router(app_settings),
        prefix="/graphql",
    )
    return application
