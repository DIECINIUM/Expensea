from uuid import UUID

from app.categorization.dto import CategoryRuleView, CorrectionView
from app.categorization.repository import CategorizationRepository
from app.db.session import Database
from app.domain.normalization import normalize_display_text
from app.ledger.errors import LedgerNotFoundError, LedgerValidationError
from app.ledger.repository import LedgerRepository


class CategorizationService:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def correct(
        self, user_id: UUID, transaction_id: UUID, category_id: UUID
    ) -> CorrectionView:
        async with self._database.session_factory()() as session, session.begin():
            ledger = LedgerRepository(session)
            if not await ledger.category_is_visible(user_id, category_id):
                raise LedgerNotFoundError(
                    code="CATEGORY_NOT_FOUND",
                    message="The selected category was not found.",
                    field="categoryId",
                )
            value = await CategorizationRepository(session).correct(
                user_id, transaction_id, category_id
            )
            if value is None:
                raise LedgerNotFoundError(
                    code="TRANSACTION_NOT_FOUND",
                    message="The transaction was not found.",
                    field="transactionId",
                )
            return value

    async def list_corrections(self, user_id: UUID) -> tuple[CorrectionView, ...]:
        async with self._database.session_factory()() as session:
            return await CategorizationRepository(session).list_corrections(user_id)

    async def create_rule(
        self, user_id: UUID, *, pattern: str, category_id: UUID, priority: int = 100
    ) -> CategoryRuleView:
        parsed = normalize_display_text(pattern).casefold()
        if not parsed or len(parsed) > 120:
            raise LedgerValidationError(
                code="INVALID_RULE_PATTERN",
                message="Rule pattern must contain 1 to 120 characters.",
                field="pattern",
            )
        if priority < 0 or priority > 1000:
            raise LedgerValidationError(
                code="INVALID_RULE_PRIORITY",
                message="Rule priority must be between 0 and 1000.",
                field="priority",
            )
        async with self._database.session_factory()() as session, session.begin():
            ledger = LedgerRepository(session)
            if not await ledger.category_is_visible(user_id, category_id):
                raise LedgerNotFoundError(
                    code="CATEGORY_NOT_FOUND",
                    message="The selected category was not found.",
                    field="categoryId",
                )
            return await CategorizationRepository(session).create_rule(
                user_id, parsed, category_id, priority
            )
