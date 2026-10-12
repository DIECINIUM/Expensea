"""Strawberry schema and FastAPI router assembly."""

from functools import partial
from typing import cast

import strawberry
from fastapi import Request
from graphql import GraphQLError, OperationType, get_operation_ast, parse
from strawberry.extensions import MaxAliasesLimiter, MaxTokensLimiter, QueryDepthLimiter
from strawberry.fastapi import GraphQLRouter

from app.ai.contracts import StructuredCompletionProvider
from app.auth.session import AuthError, authenticate_request, require_csrf
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

    async def context_getter(request: Request) -> GraphQLContext:
        try:
            principal = await authenticate_request(request)
        except AuthError:
            principal = None
        if request.method == "POST":
            try:
                payload = await request.json()
                operation = (
                    get_operation_ast(
                        parse(payload.get("query", ""), max_tokens=2_000),
                        payload.get("operationName"),
                    )
                    if isinstance(payload, dict)
                    else None
                )
            except (ValueError, GraphQLError, TypeError):
                operation = None
            if (
                operation is not None
                and operation.operation is OperationType.MUTATION
                and principal is not None
            ):
                await require_csrf(request)
        return GraphQLContext(
            settings,
            database_from_request(request),
            principal,
            cast(
                StructuredCompletionProvider,
                request.app.state.structured_provider,
            ),
        )

    return GraphQLRouter(
        schema,
        context_getter=context_getter,
        graphql_ide="graphiql" if settings.debug else None,
        allow_queries_via_get=False,
    )
