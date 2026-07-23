"""Typed dependencies available to GraphQL resolvers."""

from strawberry.fastapi import BaseContext

from app.core.config import Settings
from app.core.logging import current_request_id


class GraphQLContext(BaseContext):
    """Per-operation context.

    Domain services and data loaders can be added here in later phases. Resolvers
    should orchestrate those collaborators rather than contain business logic.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def request_id(self) -> str | None:
        """Expose the current request correlation ID to resolvers."""
        return current_request_id()
