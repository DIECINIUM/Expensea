"""Ollama-compatible schema-constrained chat provider."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.contracts import (
    ProviderTelemetry,
    StructuredCompletion,
    StructuredCompletionRequest,
)
from app.ai.errors import AIProviderError

MAX_PROVIDER_RESPONSE_BYTES = 1_048_576
_PORTABLE_DECIMAL_PATTERN = r"^-?[0-9]+(\.[0-9]+)?$"


class _OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str
    thinking: str | None = None


class _OllamaResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: _OllamaMessage
    prompt_eval_count: int | None = None
    eval_count: int | None = None


class OllamaChatProvider:
    """Call `/api/chat` and accept only a bounded JSON-object response."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(timeout_seconds, 10.0),
        )
        self._client = client

    async def complete(
        self,
        request: StructuredCompletionRequest,
    ) -> StructuredCompletion:
        started = perf_counter()
        body: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "format": _provider_compatible_schema(request.response_schema),
            "options": {
                "temperature": 0,
                "num_predict": 1024,
            },
        }
        try:
            response = await self._post(body)
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                code="AI_PROVIDER_TIMEOUT",
                message="The AI provider did not respond before the configured timeout.",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                code="AI_PROVIDER_UNAVAILABLE",
                message="The AI provider request failed.",
            ) from exc

        if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
            raise AIProviderError(
                code="AI_PROVIDER_RESPONSE_TOO_LARGE",
                message="The AI provider response exceeded the configured safety limit.",
            )
        if response.is_error:
            raise AIProviderError(
                code="AI_PROVIDER_HTTP_ERROR",
                message="The AI provider rejected the structured completion request.",
            )

        try:
            envelope = _OllamaResponse.model_validate_json(response.content)
            parsed = json.loads(envelope.message.content)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise AIProviderError(
                code="AI_PROVIDER_INVALID_RESPONSE",
                message="The AI provider returned an invalid structured response.",
            ) from exc
        if not isinstance(parsed, dict):
            raise AIProviderError(
                code="AI_PROVIDER_INVALID_RESPONSE",
                message="The AI provider response must be a JSON object.",
            )

        return StructuredCompletion(
            data=parsed,
            telemetry=ProviderTelemetry(
                provider="ollama",
                model=self._model,
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
                input_tokens=envelope.prompt_eval_count,
                output_tokens=envelope.eval_count,
            ),
        )

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(
                f"{self._base_url}/api/chat",
                json=body,
                timeout=self._timeout,
            )
        async with httpx.AsyncClient() as client:
            return await client.post(
                f"{self._base_url}/api/chat",
                json=body,
                timeout=self._timeout,
            )


def _provider_compatible_schema(value: Any) -> Any:
    """Anchor JSON Schema regexes for strict Ollama-compatible backends."""
    if isinstance(value, dict):
        compatible: dict[str, Any] = {}
        for key, item in value.items():
            if key == "pattern" and isinstance(item, str):
                # Ollama grammar backends do not consistently support the
                # lookarounds emitted for Pydantic Decimal fields. Preserve a
                # portable decimal-only hint; final Pydantic bounds and precision
                # validation remain authoritative.
                if "(?=" in item or "(?!" in item or "(?<" in item:
                    compatible[key] = _PORTABLE_DECIMAL_PATTERN
                    continue
                pattern = item if item.startswith("^") else f"^(?:{item})"
                compatible[key] = pattern if pattern.endswith("$") else f"{pattern}$"
            else:
                compatible[key] = _provider_compatible_schema(item)
        return compatible
    if isinstance(value, list):
        return [_provider_compatible_schema(item) for item in value]
    return value
