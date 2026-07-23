"""Strawberry schema and FastAPI router assembly."""

import strawberry
from strawberry.fastapi import GraphQLRouter

from app.core.config import Settings
from app.graphql.context import GraphQLContext
from app.graphql.query import Query

schema = strawberry.Schema(query=Query)


def create_graphql_router(settings: Settings) -> GraphQLRouter[GraphQLContext]:
    """Create a router whose context shares the app factory's settings."""

    async def context_getter() -> GraphQLContext:
        return GraphQLContext(settings)

    return GraphQLRouter(
        schema,
        context_getter=context_getter,
        graphql_ide="graphiql" if settings.debug else None,
        allow_queries_via_get=False,
    )
