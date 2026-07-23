"""Phase 0 GraphQL query surface."""

import strawberry
from strawberry.types import Info

from app.graphql.context import GraphQLContext


@strawberry.type
class AppInfo:
    """Non-sensitive application metadata."""

    name: str
    version: str
    environment: str


@strawberry.type
class Query:
    """Operational queries only; finance domain fields begin in Phase 1."""

    @strawberry.field
    def health(self) -> str:
        """Report GraphQL process health without probing dependencies."""
        return "ok"

    @strawberry.field
    def app_info(self, info: Info[GraphQLContext, None]) -> AppInfo:
        """Return stable metadata from the typed request context."""
        settings = info.context.settings
        return AppInfo(
            name=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env.value,
        )
