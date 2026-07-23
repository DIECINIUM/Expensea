"""Injected, lazy async SQLAlchemy engine and request-scoped sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Own one application's lazy engine and session factory."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def database_url(self) -> str:
        """Expose the configured URL for safe equality checks, not logging."""
        return self._database_url

    def engine(self) -> AsyncEngine:
        """Create the application engine only when persistence is first requested."""
        if self._engine is None:
            self._engine = create_async_engine(
                self._database_url,
                pool_pre_ping=True,
                hide_parameters=True,
            )
        return self._engine

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return this application's factory for short-lived async sessions."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine(),
                class_=AsyncSession,
                autoflush=False,
                expire_on_commit=False,
            )
        return self._session_factory

    async def dispose(self) -> None:
        """Dispose this application's engine without forcing its creation."""
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._session_factory = None


def database_from_request(request: Request) -> Database:
    """Return the database owned by the current FastAPI application."""
    return cast(Database, request.app.state.database)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield one transaction-neutral session from the current application."""
    database = database_from_request(request)
    async with database.session_factory()() as session:
        yield session
