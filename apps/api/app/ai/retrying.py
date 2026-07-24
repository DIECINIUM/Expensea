"""Bounded retries for transient structured-completion failures."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace

from app.ai.contracts import (
    StructuredCompletion,
    StructuredCompletionProvider,
    StructuredCompletionRequest,
)
from app.ai.errors import AIProviderError

Sleep = Callable[[float], Awaitable[None]]

_RETRYABLE_ERROR_CODES = frozenset(
    {
        "AI_PROVIDER_RATE_LIMITED",
        "AI_PROVIDER_TIMEOUT",
        "AI_PROVIDER_UNAVAILABLE",
    }
)


class RetryingStructuredProvider:
    """Retry only explicitly transient failures with a small deterministic bound."""

    def __init__(
        self,
        provider: StructuredCompletionProvider,
        *,
        max_attempts: int,
        backoff_seconds: float,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if max_attempts < 1 or max_attempts > 4:
            raise ValueError("max_attempts must be between 1 and 4")
        if backoff_seconds < 0 or backoff_seconds > 10:
            raise ValueError("backoff_seconds must be between 0 and 10")
        self._provider = provider
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep

    async def complete(
        self,
        request: StructuredCompletionRequest,
    ) -> StructuredCompletion:
        """Return the first successful completion or the final safe provider error."""
        for attempt in range(1, self._max_attempts + 1):
            try:
                completion = await self._provider.complete(request)
                return replace(
                    completion,
                    telemetry=replace(
                        completion.telemetry,
                        attempt_count=attempt,
                    ),
                )
            except AIProviderError as exc:
                if exc.code not in _RETRYABLE_ERROR_CODES or attempt == self._max_attempts:
                    raise
                delay = self._backoff_seconds * (2 ** (attempt - 1))
                if delay:
                    await self._sleep(delay)

        raise AssertionError("bounded provider retry loop did not terminate")
