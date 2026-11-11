"""
Structured JSON logging configuration using structlog.

WHY structlog: produces machine-parseable JSON logs that work well with
Docker log drivers, ELK/Loki, and `jq` for ad-hoc queries.  Every log
line includes a request_id for tracing a single request across all log
entries it produces.

WHY middleware for request_id: ensures every log line within a request
is automatically tagged, without requiring each endpoint to pass it.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def setup_logging(log_level: str = "info") -> None:
    """Configure structlog for JSON output to stdout.

    Called once at app startup.  Processors run in order:
    1. add_log_level          — injects "level" key
    2. TimeStamper            — ISO-8601 timestamp as "ts"
    3. JSONRenderer           — final output as one JSON line
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # picks up request_id etc.
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_level_name_to_int(log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _level_name_to_int(level: str) -> int:
    """Convert a level name to structlog's numeric level."""
    mapping = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}
    return mapping.get(level.lower(), 20)


def get_logger(**kwargs):
    """Return a bound structlog logger.  Convenience wrapper."""
    return structlog.get_logger(**kwargs)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that assigns a unique request ID to every HTTP request.

    WHY: enables correlating all log lines and audit events produced
    during a single request.  If the client sends X-Request-ID we reuse
    it (useful for distributed tracing); otherwise we generate a UUID.
    The ID is returned in the response header so the client can quote it
    in bug reports.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Reuse client-provided ID or generate one
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.perf_counter()

        # Bind request_id into structlog context for all downstream loggers
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        logger = get_logger()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled_error",
                method=request.method,
                path=request.url.path,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Log every completed request with key fields for debugging
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )

        # Return request_id in response so clients can reference it
        response.headers["X-Request-ID"] = request_id
        return response
