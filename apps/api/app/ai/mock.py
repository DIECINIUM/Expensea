"""Deterministic structured provider for tests and local offline demos."""

from collections.abc import Iterable

from app.ai.contracts import (
    ProviderTelemetry,
    StructuredCompletion,
    StructuredCompletionRequest,
)
from app.ai.errors import AIProviderError


class MockStructuredProvider:
    """Return queued JSON objects and retain requests without network calls."""

    def __init__(self, responses: Iterable[dict[str, object]]) -> None:
        self._responses = list(responses)
        self.requests: list[StructuredCompletionRequest] = []

    async def complete(
        self,
        request: StructuredCompletionRequest,
    ) -> StructuredCompletion:
        self.requests.append(request)
        if not self._responses:
            raise AIProviderError(
                code="MOCK_PROVIDER_EXHAUSTED",
                message="The deterministic mock provider has no remaining response.",
            )
        return StructuredCompletion(
            data=self._responses.pop(0),
            telemetry=ProviderTelemetry(
                provider="mock",
                model="deterministic-fixture",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
            ),
        )
