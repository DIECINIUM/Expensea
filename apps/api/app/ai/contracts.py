"""Provider-neutral structured completion request and result types."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StructuredCompletionRequest:
    """One schema-constrained interpretation request."""

    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any]
    prompt_name: str
    prompt_version: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class ProviderTelemetry:
    """Content-free provider metadata safe for persistence and diagnostics."""

    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class StructuredCompletion:
    """Validated JSON object plus non-sensitive call metadata."""

    data: dict[str, Any]
    telemetry: ProviderTelemetry


class StructuredCompletionProvider(Protocol):
    """Interpret untrusted text without business writes or tool access."""

    async def complete(
        self,
        request: StructuredCompletionRequest,
    ) -> StructuredCompletion:
        """Return one JSON object matching the requested schema."""
        ...
