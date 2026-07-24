"""Authentication and sanitized resolver execution helpers."""

import logging
from collections.abc import Awaitable
from uuid import UUID

from graphql import GraphQLError

from app.graphql.context import GraphQLContext
from app.ledger.errors import LedgerError

logger = logging.getLogger("app.graphql")


def require_user_id(context: GraphQLContext) -> UUID:
    """Require server-authenticated identity without accepting client owner IDs."""
    if context.principal is None:
        raise GraphQLError(
            "Authentication is required.",
            extensions={"code": "UNAUTHENTICATED", "requestId": context.request_id},
        )
    return context.principal.user_id


async def resolve_safely[Result](
    operation: Awaitable[Result],
    context: GraphQLContext,
) -> Result:
    """Expose stable domain failures while masking unexpected details."""
    try:
        return await operation
    except LedgerError as exc:
        extensions: dict[str, str | None] = {
            "code": exc.code,
            "requestId": context.request_id,
        }
        if exc.field is not None:
            extensions["field"] = exc.field
        raise GraphQLError(exc.message, extensions=extensions) from None
    except Exception as exc:
        logger.error(
            "graphql.resolver_failed",
            extra={
                "error_type": type(exc).__name__,
                "request_id": context.request_id,
            },
        )
        raise GraphQLError(
            "Internal server error.",
            extensions={"code": "INTERNAL", "requestId": context.request_id},
        ) from None
