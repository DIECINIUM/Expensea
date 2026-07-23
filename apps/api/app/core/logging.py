"""Structured JSON logging and request correlation."""

from __future__ import annotations

import json
import logging
import logging.config
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, ClassVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    """Return the correlation ID bound to the current async context."""
    return _request_id.get()


def bind_request_id(value: str) -> Token[str | None]:
    """Bind a correlation ID and return the token required to reset it."""
    return _request_id.set(value)


class JsonFormatter(logging.Formatter):
    """Serialize standard records plus explicitly supplied metadata as JSON."""

    _reserved: ClassVar[set[str]] = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Render a stable log envelope suitable for aggregation."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = current_request_id()
        if request_id is not None:
            payload["request_id"] = request_id

        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in self._reserved and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str) -> None:
    """Configure one JSON stream for application and server logs."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.access": {
                    # The default access message contains the raw query string.
                    # RequestContextMiddleware emits the safe path-only event.
                    "handlers": [],
                    "level": "WARNING",
                    "propagate": False,
                },
            },
        }
    )


def _request_id_from(request: Request) -> str:
    candidate = request.headers.get(REQUEST_ID_HEADER, "")
    return candidate if _REQUEST_ID_PATTERN.fullmatch(candidate) else uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlate each HTTP request and emit one structured completion event."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = _request_id_from(request)
        token = bind_request_id(request_id)
        request.state.request_id = request_id
        started_at = perf_counter()
        logger = logging.getLogger("app.request")

        try:
            response = await call_next(request)
        except Exception as exc:
            # Exception messages and tracebacks can contain financial inputs or SQL
            # parameters. Record the stable type and request metadata only; attach
            # a redacted error backend in a later observability phase.
            logger.error(
                "request.failed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    "error_type": type(exc).__name__,
                },
            )
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=500,
                headers={REQUEST_ID_HEADER: request_id},
            )
        else:
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request.completed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            return response
        finally:
            _request_id.reset(token)
