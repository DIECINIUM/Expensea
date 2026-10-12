"""Bounded operational telemetry without request bodies, URLs, or financial data."""

from __future__ import annotations

import hmac
import os
from asyncio import timeout
from time import perf_counter
from typing import cast

from fastapi import APIRouter, HTTPException, Request
from opentelemetry import propagate
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.ai.contracts import (
    StructuredCompletion,
    StructuredCompletionProvider,
    StructuredCompletionRequest,
)
from app.db.session import Database

router = APIRouter(tags=["operations"])


class OperationalTelemetry:
    def __init__(self, *, otlp_endpoint: str = "", metrics_token: str = "") -> None:
        self.metrics_token = metrics_token
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "spendgraph_http_requests_total",
            "Completed API requests by bounded route, method, and status.",
            ["route", "method", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "spendgraph_http_duration_seconds",
            "API request latency.",
            ["route", "method"],
            registry=self.registry,
        )
        self.ai_calls = Counter(
            "spendgraph_ai_calls_total",
            "Structured provider calls; failure includes unavailable and invalid responses.",
            ["outcome"],
            registry=self.registry,
        )
        self.ai_duration = Histogram(
            "spendgraph_ai_duration_seconds",
            "Structured provider latency including bounded retries.",
            registry=self.registry,
        )
        self.ai_tokens = Counter(
            "spendgraph_ai_tokens_total",
            "Reported provider token usage; unreported usage is not estimated.",
            ["direction"],
            registry=self.registry,
        )
        self.provider = TracerProvider(resource=Resource.create({"service.name": "spendgraph-api"}))
        if otlp_endpoint:
            self.provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, timeout=5))
            )
        self.tracer = self.provider.get_tracer("spendgraph.api")

    @classmethod
    def from_environment(cls) -> OperationalTelemetry:
        return cls(
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", ""),
            metrics_token=os.getenv("METRICS_TOKEN", ""),
        )

    def shutdown(self) -> None:
        self.provider.shutdown()


class TelemetryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, telemetry: OperationalTelemetry) -> None:
        super().__init__(app)
        self.telemetry = telemetry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        method = request.method if request.method in {"GET", "POST", "OPTIONS"} else "OTHER"
        with self.telemetry.tracer.start_as_current_span(
            "HTTP request",
            context=propagate.extract(dict(request.headers)),
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            response = await call_next(request)
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            # Matched route templates keep user identifiers and arbitrary paths out.
            route_label = str(route_path) if route is not None else "unmatched"
            span.update_name(f"{method} {route_label}")
            span.set_attribute("http.request.method", method)
            span.set_attribute("http.route", route_label)
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            self.telemetry.requests.labels(route_label, method, str(response.status_code)).inc()
            self.telemetry.duration.labels(route_label, method).observe(perf_counter() - started)
            return response


class ObservedProvider:
    def __init__(
        self, provider: StructuredCompletionProvider, telemetry: OperationalTelemetry
    ) -> None:
        self.provider = provider
        self.telemetry = telemetry

    async def complete(self, request: StructuredCompletionRequest) -> StructuredCompletion:
        started = perf_counter()
        succeeded = False
        with self.telemetry.tracer.start_as_current_span(
            "AI structured completion",
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                result = await self.provider.complete(request)
                for direction, tokens in (
                    ("input", result.telemetry.input_tokens),
                    ("output", result.telemetry.output_tokens),
                ):
                    if tokens is not None:
                        self.telemetry.ai_tokens.labels(direction).inc(tokens)
                succeeded = True
                return result
            finally:
                outcome = "success" if succeeded else "failure"
                self.telemetry.ai_calls.labels(outcome).inc()
                self.telemetry.ai_duration.observe(perf_counter() - started)
                span.set_attribute("ai.outcome", outcome)
                if not succeeded:
                    span.set_status(Status(StatusCode.ERROR))


@router.get("/ready")
async def readiness(request: Request) -> Response:
    database = cast(Database, request.app.state.database)
    try:
        async with timeout(3):
            async with database.engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, TimeoutError):
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ready"})


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    telemetry = cast(OperationalTelemetry, request.app.state.telemetry)
    if not telemetry.metrics_token:
        raise HTTPException(status_code=404, detail="Metrics are not enabled.")
    authorization = request.headers.get("Authorization", "")
    if not hmac.compare_digest(authorization, f"Bearer {telemetry.metrics_token}"):
        raise HTTPException(status_code=401, detail="Metrics authorization required.")
    return Response(
        generate_latest(telemetry.registry), headers={"Content-Type": CONTENT_TYPE_LATEST}
    )
