"""Opt-in synthetic contract check for a configured live Ollama-compatible host."""

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.ai.extraction import FinancialNoteExtractor, NoteExtractionContext
from app.ai.factory import create_structured_provider
from app.core.config import Settings


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_AI_TESTS") != "1",
    reason="set RUN_LIVE_AI_TESTS=1 to call the configured model host",
)
async def test_configured_live_provider_returns_schema_valid_synthetic_event() -> None:
    settings = Settings(_env_file=None)
    extractor = FinancialNoteExtractor(
        create_structured_provider(settings),
        max_input_chars=settings.ai_max_input_chars,
        review_confidence_threshold=Decimal(str(settings.ai_review_confidence_threshold)),
    )

    result = await extractor.extract(
        "Paid ₹249 for a synthetic music subscription today.",
        NoteExtractionContext(
            source_timestamp=datetime(2026, 7, 24, 4, 30, tzinfo=UTC),
            timezone="Asia/Kolkata",
            default_currency="INR",
        ),
    )

    assert result.event.currency == "INR"
    assert result.event.amount == Decimal("249")
    assert result.requires_review is True
