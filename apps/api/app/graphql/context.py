"""Typed dependencies available to GraphQL resolvers."""

from strawberry.fastapi import BaseContext

from app.auth.principal import Principal
from app.core.config import Settings
from app.core.logging import current_request_id
from app.db.session import Database
from app.ledger.obligation_service import ObligationService
from app.ledger.recurring_service import RecurringPaymentService
from app.ledger.service import LedgerService


class GraphQLContext(BaseContext):
    """Per-operation context.

    The context holds trusted identity and stateless service collaborators. The
    service opens a short-lived session per root field, so concurrently resolved
    dashboard fields never share an ``AsyncSession``.
    """

    def __init__(
        self,
        settings: Settings,
        database: Database,
        principal: Principal | None,
    ) -> None:
        self.settings = settings
        self.principal = principal
        self.ledger = LedgerService(database)
        self.obligations = ObligationService(database)
        self.recurring = RecurringPaymentService(database)

    @property
    def request_id(self) -> str | None:
        """Expose the current request correlation ID to resolvers."""
        return current_request_id()
