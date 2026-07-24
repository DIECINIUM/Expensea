"""Contract tests for the Ollama-compatible structured chat adapter."""

import json

import httpx
import pytest

from app.ai.contracts import StructuredCompletionRequest
from app.ai.errors import AIProviderError
from app.ai.ollama import OllamaChatProvider


def _request() -> StructuredCompletionRequest:
    return StructuredCompletionRequest(
        system_prompt="Return the schema only.",
        user_prompt="UNTRUSTED_NOTE\nSynthetic expense\nEND_UNTRUSTED_NOTE",
        response_schema={
            "type": "object",
            "properties": {"event_kind": {"type": "string"}},
            "required": ["event_kind"],
            "additionalProperties": False,
        },
        prompt_name="test",
        prompt_version="1",
        schema_version="test/v1",
    )


@pytest.mark.asyncio
async def test_ollama_adapter_sends_schema_and_discards_reasoning_trace() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"event_kind":"expense"}',
                    "thinking": "This private reasoning must never be returned.",
                },
                "prompt_eval_count": 42,
                "eval_count": 7,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaChatProvider(
            base_url="http://ollama.example.test",
            model="gemma4:e4b",
            timeout_seconds=10,
            client=client,
        )
        completion = await provider.complete(_request())

    assert captured["model"] == "gemma4:e4b"
    assert captured["stream"] is False
    assert captured["think"] is False
    assert captured["format"] == _request().response_schema
    assert captured["options"] == {"temperature": 0, "num_predict": 1024}
    assert completion.data == {"event_kind": "expense"}
    assert completion.telemetry.provider == "ollama"
    assert completion.telemetry.model == "gemma4:e4b"
    assert completion.telemetry.input_tokens == 42
    assert completion.telemetry.output_tokens == 7
    assert "reasoning" not in completion.data


@pytest.mark.asyncio
async def test_ollama_adapter_anchors_nested_schema_patterns() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"amount":"249.0000"}',
                },
            },
        )

    request = _request()
    request = StructuredCompletionRequest(
        system_prompt=request.system_prompt,
        user_prompt=request.user_prompt,
        response_schema={
            "type": "object",
            "properties": {
                "amount": {
                    "anyOf": [
                        {"type": "string", "pattern": r"^\d+(?:\.\d{1,4})?"},
                        {"type": "null"},
                    ]
                }
            },
        },
        prompt_name=request.prompt_name,
        prompt_version=request.prompt_version,
        schema_version=request.schema_version,
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaChatProvider(
            base_url="http://ollama.example.test",
            model="gemma4:e4b",
            timeout_seconds=10,
            client=client,
        )
        await provider.complete(request)

    schema = captured["format"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    amount = properties["amount"]
    assert isinstance(amount, dict)
    variants = amount["anyOf"]
    assert isinstance(variants, list)
    assert variants[0]["pattern"] == r"^\d+(?:\.\d{1,4})?$"


@pytest.mark.asyncio
async def test_ollama_adapter_replaces_unsupported_lookaround_patterns() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": '{"amount":"249"}'}},
        )

    request = _request()
    request = StructuredCompletionRequest(
        system_prompt=request.system_prompt,
        user_prompt=request.user_prompt,
        response_schema={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "string",
                    "pattern": r"^(?![-+.]*$)\d+(?=\.\d{1,4}$)",
                }
            },
        },
        prompt_name=request.prompt_name,
        prompt_version=request.prompt_version,
        schema_version=request.schema_version,
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaChatProvider(
            base_url="http://ollama.example.test",
            model="gemma4:e4b",
            timeout_seconds=10,
            client=client,
        )
        await provider.complete(request)

    schema = captured["format"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    amount = properties["amount"]
    assert isinstance(amount, dict)
    assert amount["pattern"] == r"^-?[0-9]+(\.[0-9]+)?$"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"error": "unavailable"}),
        httpx.Response(200, json={"message": {"role": "assistant", "content": "not-json"}}),
        httpx.Response(200, json={"message": {"role": "assistant", "content": "[]"}}),
    ],
)
async def test_ollama_adapter_fails_closed_on_invalid_provider_responses(
    response: httpx.Response,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaChatProvider(
            base_url="http://ollama.example.test",
            model="gemma4:e4b",
            timeout_seconds=10,
            client=client,
        )
        with pytest.raises(AIProviderError):
            await provider.complete(_request())


@pytest.mark.asyncio
async def test_ollama_adapter_maps_timeout_without_prompt_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaChatProvider(
            base_url="http://ollama.example.test",
            model="gemma4:e4b",
            timeout_seconds=1,
            client=client,
        )
        with pytest.raises(AIProviderError) as exc_info:
            await provider.complete(_request())

    assert exc_info.value.code == "AI_PROVIDER_TIMEOUT"
    assert "Synthetic expense" not in str(exc_info.value)
