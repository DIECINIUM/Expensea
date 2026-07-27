from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.categorization.dto import CategoryAssignment, CategoryRuleView, CorrectionView
from app.categorization.policy import CLASSIFIER_VERSION, retrieval_assignment
from app.domain.enums import CategorizationSource
from app.models import (
    Category,
    CategoryRule,
    LedgerTransaction,
    Merchant,
    MerchantCategoryMap,
    UserCorrection,
)


class CategorizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def classify(
        self, user_id: UUID, *, description: str, merchant_normalized_name: str | None
    ) -> CategoryAssignment | None:
        normalized = description.casefold()
        rules = (
            await self._session.execute(
                select(CategoryRule.normalized_pattern, CategoryRule.category_id)
                .where(CategoryRule.user_id == user_id, CategoryRule.enabled.is_(True))
                .order_by(CategoryRule.priority, CategoryRule.created_at, CategoryRule.id)
            )
        ).all()
        for pattern, category_id in rules:
            if pattern in normalized:
                return CategoryAssignment(
                    category_id,
                    CategorizationSource.USER_RULE,
                    CLASSIFIER_VERSION,
                    Decimal("1.0000"),
                )

        merchant_id: UUID | None = None
        if merchant_normalized_name:
            merchant_id = cast(
                UUID | None,
                await self._session.scalar(
                    select(Merchant.id).where(Merchant.normalized_name == merchant_normalized_name)
                ),
            )
        if merchant_id:
            mapped = cast(
                UUID | None,
                await self._session.scalar(
                    select(MerchantCategoryMap.category_id).where(
                        MerchantCategoryMap.user_id == user_id,
                        MerchantCategoryMap.merchant_id == merchant_id,
                        MerchantCategoryMap.verified.is_(True),
                    )
                ),
            )
            if mapped:
                return CategoryAssignment(
                    mapped, CategorizationSource.MERCHANT_MAP, CLASSIFIER_VERSION, Decimal("1.0000")
                )

        exact = cast(
            UUID | None,
            await self._session.scalar(
                select(UserCorrection.corrected_category_id)
                .where(
                    UserCorrection.user_id == user_id,
                    UserCorrection.normalized_description == normalized,
                )
                .order_by(UserCorrection.created_at.desc(), UserCorrection.id.desc())
                .limit(1)
            ),
        )
        if exact:
            return CategoryAssignment(
                exact,
                CategorizationSource.VERIFIED_CORRECTION,
                CLASSIFIER_VERSION,
                Decimal("1.0000"),
            )

        rows = (
            await self._session.execute(
                select(UserCorrection.normalized_description, UserCorrection.corrected_category_id)
                .where(UserCorrection.user_id == user_id)
                .order_by(UserCorrection.created_at.desc())
                .limit(200)
            )
        ).all()
        return retrieval_assignment(normalized, tuple((row[0], row[1]) for row in rows))

    async def correct(
        self, user_id: UUID, transaction_id: UUID, category_id: UUID
    ) -> CorrectionView | None:
        transaction = await self._session.scalar(
            select(LedgerTransaction)
            .where(LedgerTransaction.user_id == user_id, LedgerTransaction.id == transaction_id)
            .with_for_update()
        )
        if transaction is None:
            return None
        previous_id = transaction.category_id
        correction = UserCorrection(
            user_id=user_id,
            transaction_id=transaction.id,
            previous_category_id=previous_id,
            corrected_category_id=category_id,
            merchant_id=transaction.merchant_id,
            normalized_description=transaction.description.casefold(),
            classifier_version=CLASSIFIER_VERSION,
            confidence=Decimal("1.0000"),
        )
        self._session.add(correction)
        transaction.category_id = category_id
        transaction.category_source = CategorizationSource.USER_OVERRIDE
        transaction.category_classifier_version = CLASSIFIER_VERSION
        transaction.category_confidence = Decimal("1.0000")
        transaction.category_overridden = True
        if transaction.merchant_id:
            await self._session.execute(
                pg_insert(MerchantCategoryMap)
                .values(
                    user_id=user_id,
                    merchant_id=transaction.merchant_id,
                    category_id=category_id,
                    verified=True,
                )
                .on_conflict_do_update(
                    index_elements=[MerchantCategoryMap.user_id, MerchantCategoryMap.merchant_id],
                    set_={"category_id": category_id, "verified": True},
                )
            )
        await self._session.flush()
        names = (
            await self._session.execute(
                select(Category.id, Category.name).where(
                    Category.id.in_([value for value in (previous_id, category_id) if value])
                )
            )
        ).all()
        by_id: dict[UUID, str] = {
            category_key: category_name for category_key, category_name in names
        }
        return CorrectionView(
            correction.id,
            transaction.id,
            by_id.get(previous_id) if previous_id is not None else None,
            by_id[category_id],
            correction.classifier_version,
            correction.confidence,
            correction.created_at,
        )

    async def list_corrections(self, user_id: UUID) -> tuple[CorrectionView, ...]:
        previous = Category.__table__.alias("previous_category")
        corrected = Category.__table__.alias("corrected_category")
        rows = (
            await self._session.execute(
                select(UserCorrection, previous.c.name, corrected.c.name)
                .outerjoin(previous, previous.c.id == UserCorrection.previous_category_id)
                .join(corrected, corrected.c.id == UserCorrection.corrected_category_id)
                .where(UserCorrection.user_id == user_id)
                .order_by(UserCorrection.created_at.desc(), UserCorrection.id.desc())
                .limit(100)
            )
        ).all()
        return tuple(
            CorrectionView(
                row.id,
                row.transaction_id,
                previous_name,
                corrected_name,
                row.classifier_version,
                row.confidence,
                row.created_at,
            )
            for row, previous_name, corrected_name in rows
        )

    async def create_rule(
        self, user_id: UUID, pattern: str, category_id: UUID, priority: int
    ) -> CategoryRuleView:
        rule = CategoryRule(
            user_id=user_id, normalized_pattern=pattern, category_id=category_id, priority=priority
        )
        self._session.add(rule)
        await self._session.flush()
        category_name = cast(
            str, await self._session.scalar(select(Category.name).where(Category.id == category_id))
        )
        return CategoryRuleView(rule.id, pattern, category_id, category_name, priority, True)
