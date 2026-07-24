"""Strawberry schema and FastAPI router assembly."""

from functools import partial

import strawberry
from fastapi import Request
from strawberry.extensions import MaxAliasesLimiter, MaxTokensLimiter, QueryDepthLimiter
from strawberry.fastapi import GraphQLRouter

from app.auth.authenticator import DevelopmentAuthenticator
from app.core.config import Settings
from app.db.session import database_from_request
from app.graphql.context import GraphQLContext
from app.graphql.mutation import Mutation
from app.graphql.query import Query

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[
        partial(QueryDepthLimiter, max_depth=10),
        partial(MaxAliasesLimiter, max_alias_count=30),
        partial(MaxTokensLimiter, max_token_count=2_000),
    ],
)


def create_graphql_router(settings: Settings) -> GraphQLRouter[GraphQLContext]:
    """Create a router whose context shares the app factory's settings."""

    authenticator = (
        DevelopmentAuthenticator(settings.dev_user_id) if settings.dev_auth_enabled else None
    )

    async def context_getter(request: Request) -> GraphQLContext:
        principal = await authenticator.authenticate(request) if authenticator is not None else None
        return GraphQLContext(
            settings,
            database_from_request(request),
            principal,
        )

    return GraphQLRouter(
        schema,
        context_getter=context_getter,
        graphql_ide="graphiql" if settings.debug else None,
        allow_queries_via_get=False,
    )
