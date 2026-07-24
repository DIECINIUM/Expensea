"""Phase 1 GraphQL mutations."""

from uuid import UUID

import strawberry
from strawberry.types import Info

from app.graphql.context import GraphQLContext
from app.graphql.mappers import (
    map_category,
    map_transaction,
    to_domain_transaction_status,
    to_domain_transaction_type,
)
from app.graphql.safety import require_user_id
from app.graphql.types import (
    ConflictProblem,
    CreateCategoryInput,
    CreateCategoryResult,
    CreateCategorySuccess,
    CreateTransactionInput,
    CreateTransactionResult,
    CreateTransactionSuccess,
    NotFoundProblem,
    ValidationProblem,
)
from app.ledger.commands import parse_create_category, parse_create_transaction
from app.ledger.errors import (
    LedgerConflictError,
    LedgerNotFoundError,
    LedgerValidationError,
)


@strawberry.type
class Mutation:
    """Validated commands; resolvers contain no financial calculations."""

    @strawberry.mutation
    async def create_transaction(
        self,
        info: Info[GraphQLContext, None],
        input: CreateTransactionInput,
    ) -> CreateTransactionResult:
        """Persist one manual transaction for the authenticated principal."""
        user_id = require_user_id(info.context)
        try:
            category_id = UUID(str(input.category_id)) if input.category_id else None
        except ValueError:
            return ValidationProblem(
                code="INVALID_CATEGORY_ID",
                message="Category ID must be a UUID.",
                field="categoryId",
            )

        try:
            command = parse_create_transaction(
                amount=input.amount,
                currency=input.currency,
                transaction_type=to_domain_transaction_type(input.transaction_type),
                description=input.description,
                transaction_date=input.transaction_date,
                status=to_domain_transaction_status(input.status),
                category_id=category_id,
                merchant_name=input.merchant_name,
            )
            created = await info.context.ledger.create_transaction(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerNotFoundError as exc:
            return NotFoundProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerConflictError as exc:
            return ConflictProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )

        return CreateTransactionSuccess(transaction=map_transaction(created))

    @strawberry.mutation
    async def create_category(
        self,
        info: Info[GraphQLContext, None],
        input: CreateCategoryInput,
    ) -> CreateCategoryResult:
        """Create a private category for the authenticated principal."""
        user_id = require_user_id(info.context)
        try:
            parent_id = (
                UUID(str(input.parent_category_id))
                if input.parent_category_id is not None
                else None
            )
        except ValueError:
            return ValidationProblem(
                code="INVALID_PARENT_CATEGORY_ID",
                message="Parent category ID must be a UUID.",
                field="parentCategoryId",
            )

        try:
            command = parse_create_category(
                name=input.name,
                parent_category_id=parent_id,
            )
            created = await info.context.ledger.create_category(user_id, command)
        except LedgerValidationError as exc:
            return ValidationProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerNotFoundError as exc:
            return NotFoundProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        except LedgerConflictError as exc:
            return ConflictProblem(
                code=exc.code,
                message=exc.message,
                field=exc.field,
            )
        return CreateCategorySuccess(category=map_category(created))
