"""Bounded retry policy tests for structured completion providers."""

from __future__ import annotations

import pytest

from app.ai.contracts import (
    ProviderTelemetry,
    StructuredCompletion,
    StructuredCompletionRequest,
)
from app.ai.errors import AIProviderError
from app.ai.retrying import RetryingStructuredProvider


def _request() -> StructuredCompletionRequest:
    return StructuredCompletionRequest(
        system_prompt="Return JSON.",
        user_prompt="UNTRUSTED_NOTE\nSynthetic\nEND_UNTRUSTED_NOTE",
        response_schema={"type": "object"},
        prompt_name="test",
        prompt_version="1",
        schema_version="test/v1",
    )


class _SequenceProvider:
    def __init__(
        self,
        outcomes: list[StructuredCompletion | AIProviderError],
    ) -> None:
        self._outcomes = outcomes
        self.calls = 0

    async def complete(
        self,
        request: StructuredCompletionRequest,
    ) -> StructuredCompletion:
        del request
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, AIProviderError):
            raise outcome
        return outcome


def _completion() -> StructuredCompletion:
    return StructuredCompletion(
        data={"event_kind": "expense"},
        telemetry=ProviderTelemetry(
            provider="test",
            model="fixture",
            latency_ms=5,
        ),
    )


@pytest.mark.asyncio
async def test_transient_failure_retries_then_records_attempt_count() -> None:
    provider = _SequenceProvider(
        [
            AIProviderError(code="AI_PROVIDER_TIMEOUT", message="Timed out."),
            _completion(),
        ]
    )
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    retrying = RetryingStructuredProvider(
        provider,
        max_attempts=3,
        backoff_seconds=0.25,
        sleep=record_sleep,
    )

    result = await retrying.complete(_request())

    assert provider.calls == 2
    assert delays == [0.25]
    assert result.telemetry.attempt_count == 2


@pytest.mark.asyncio
async def test_non_transient_failure_is_not_retried() -> None:
    provider = _SequenceProvider(
        [
            AIProviderError(
                code="AI_PROVIDER_INVALID_RESPONSE",
                message="Invalid response.",
            ),
            _completion(),
        ]
    )
    retrying = RetryingStructuredProvider(
        provider,
        max_attempts=3,
        backoff_seconds=0,
    )

    with pytest.raises(AIProviderError) as exc_info:
        await retrying.complete(_request())

    assert exc_info.value.code == "AI_PROVIDER_INVALID_RESPONSE"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_transient_failures_stop_at_the_configured_bound() -> None:
    unavailable = AIProviderError(
        code="AI_PROVIDER_UNAVAILABLE",
        message="Unavailable.",
    )
    provider = _SequenceProvider([unavailable, unavailable, unavailable])
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    retrying = RetryingStructuredProvider(
        provider,
        max_attempts=3,
        backoff_seconds=0.1,
        sleep=record_sleep,
    )

    with pytest.raises(AIProviderError) as exc_info:
        await retrying.complete(_request())

    assert exc_info.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert provider.calls == 3
    assert sleeps == [0.1, 0.2]


@pytest.mark.parametrize(
    ("max_attempts", "backoff_seconds"),
    [(0, 0), (5, 0), (1, -0.1), (1, 10.1)],
)
def test_retry_configuration_is_bounded(
    max_attempts: int,
    backoff_seconds: float,
) -> None:
    provider = _SequenceProvider([_completion()])
    with pytest.raises(ValueError):
        RetryingStructuredProvider(
            provider,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
        )
