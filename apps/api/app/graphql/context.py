"""Typed dependencies available to GraphQL resolvers."""

from decimal import Decimal

from strawberry.fastapi import BaseContext

from app.ai.contracts import StructuredCompletionProvider
from app.ai.extraction import FinancialNoteExtractor
from app.ai.proposal_service import FinancialProposalService
from app.auth.principal import Principal
from app.categorization.service import CategorizationService
from app.core.config import Settings
from app.core.logging import current_request_id
from app.db.session import Database
from app.ledger.obligation_service import ObligationService
from app.ledger.recurring_service import RecurringPaymentService
from app.ledger.service import LedgerService
from app.reconciliation.policy import ReconciliationPolicy
from app.reconciliation.service import ReconciliationService


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
        structured_provider: StructuredCompletionProvider,
    ) -> None:
        self.settings = settings
        self.principal = principal
        self.ledger = LedgerService(database)
        self.categorization = CategorizationService(database)
        self.obligations = ObligationService(database)
        self.recurring = RecurringPaymentService(database)
        reconciliation_policy = ReconciliationPolicy(
            candidate_window_minutes=settings.reconciliation_candidate_window_minutes,
            max_candidates=settings.reconciliation_max_candidates,
            possible_duplicate_threshold=settings.reconciliation_possible_duplicate_threshold,
            auto_merge_threshold=settings.reconciliation_auto_merge_threshold,
            amount_weight=settings.reconciliation_amount_weight,
            time_weight=settings.reconciliation_time_weight,
            merchant_weight=settings.reconciliation_merchant_weight,
            description_weight=settings.reconciliation_description_weight,
        )
        self.reconciliation = ReconciliationService(
            database,
            reconciliation_policy,
        )
        self.proposals = FinancialProposalService(
            database,
            FinancialNoteExtractor(
                structured_provider,
                max_input_chars=settings.ai_max_input_chars,
                review_confidence_threshold=Decimal(str(settings.ai_review_confidence_threshold)),
            ),
            reconciliation_policy=reconciliation_policy,
        )

    @property
    def request_id(self) -> str | None:
        """Expose the current request correlation ID to resolvers."""
        return current_request_id()
