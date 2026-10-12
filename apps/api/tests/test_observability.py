import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from app.ai.contracts import ProviderTelemetry, StructuredCompletion, StructuredCompletionRequest
from app.core.logging import RequestContextMiddleware
from app.core.observability import (
    ObservedProvider,
    OperationalTelemetry,
    TelemetryMiddleware,
    router,
)


@pytest.mark.asyncio
async def test_metrics_require_secret_and_use_route_templates() -> None:
    app = FastAPI()
    telemetry = OperationalTelemetry(metrics_token="test-operational-token")
    app.state.telemetry = telemetry
    app.add_middleware(TelemetryMiddleware, telemetry=telemetry)
    app.include_router(router)

    @app.get("/example/{record_id}")
    async def example(record_id: str) -> dict[str, bool]:
        return {"ok": bool(record_id)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.get("/example/private-record?secret=private-value")
        assert (await client.get("/metrics")).status_code == 401
        result = await client.get(
            "/metrics", headers={"Authorization": "Bearer test-operational-token"}
        )
    assert result.status_code == 200
    assert 'route="/example/{record_id}"' in result.text
    assert "private-record" not in result.text
    assert "private-value" not in result.text
    telemetry.shutdown()


@pytest.mark.asyncio
async def test_metrics_disabled_by_default() -> None:
    app = FastAPI()
    telemetry = OperationalTelemetry()
    app.state.telemetry = telemetry
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/metrics")).status_code == 404
    telemetry.shutdown()


@pytest.mark.asyncio
async def test_error_traces_never_capture_exception_content() -> None:
    app = FastAPI()
    telemetry = OperationalTelemetry()
    exporter = InMemorySpanExporter()
    telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(TelemetryMiddleware, telemetry=telemetry)

    @app.get("/failure/{record_id}")
    async def failure(record_id: str) -> None:
        raise ValueError(f"private financial data: {record_id}")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/failure/private-record?secret=private-value")
    assert response.status_code == 500
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "GET /failure/{record_id}"
    assert not spans[0].events
    assert "private-record" not in str(spans[0].attributes)
    assert "private-value" not in str(spans[0].attributes)
    telemetry.shutdown()


@pytest.mark.asyncio
async def test_provider_metrics_count_reported_usage_and_propagate_failures() -> None:
    class Provider:
        async def complete(self, request: StructuredCompletionRequest) -> StructuredCompletion:
            if request.user_prompt == "fail":
                raise ValueError("private provider error")
            return StructuredCompletion(
                data={"private": request.user_prompt},
                telemetry=ProviderTelemetry(
                    provider="test", model="test", latency_ms=1, input_tokens=3, output_tokens=2
                ),
            )

    telemetry = OperationalTelemetry()
    provider = ObservedProvider(Provider(), telemetry)
    request = StructuredCompletionRequest(
        system_prompt="trusted",
        user_prompt="private note",
        response_schema={},
        prompt_name="test",
        prompt_version="1",
        schema_version="1",
    )
    assert (await provider.complete(request)).data == {"private": "private note"}
    with pytest.raises(ValueError, match="private provider error"):
        await provider.complete(
            StructuredCompletionRequest(
                system_prompt="trusted",
                user_prompt="fail",
                response_schema={},
                prompt_name="test",
                prompt_version="1",
                schema_version="1",
            )
        )
    metrics_text = generate_latest(telemetry.registry).decode()
    assert 'spendgraph_ai_calls_total{outcome="success"} 1.0' in metrics_text
    assert 'spendgraph_ai_calls_total{outcome="failure"} 1.0' in metrics_text
    assert 'spendgraph_ai_tokens_total{direction="input"} 3.0' in metrics_text
    assert "private note" not in metrics_text
    assert "private provider error" not in metrics_text
    telemetry.shutdown()
