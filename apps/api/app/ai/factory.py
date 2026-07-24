"""Build the configured provider without network work at application startup."""

import httpx

from app.ai.contracts import (
    StructuredCompletion,
    StructuredCompletionProvider,
    StructuredCompletionRequest,
)
from app.ai.errors import AIProviderError
from app.ai.ollama import OllamaChatProvider
from app.core.config import AIProvider, Settings


class DisabledStructuredProvider:
    """Fail closed when structured interpretation is not configured."""

    async def complete(
        self,
        request: StructuredCompletionRequest,
    ) -> StructuredCompletion:
        del request
        raise AIProviderError(
            code="AI_PROVIDER_DISABLED",
            message="Structured AI extraction is disabled.",
        )


def create_structured_provider(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> StructuredCompletionProvider:
    """Return a lazy provider adapter from validated server-only settings."""
    if settings.ai_provider is AIProvider.OLLAMA:
        return OllamaChatProvider(
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            timeout_seconds=settings.ai_request_timeout_seconds,
            client=client,
        )
    return DisabledStructuredProvider()
