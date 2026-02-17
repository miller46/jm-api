from __future__ import annotations

import time
from uuid import uuid4

import structlog
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a stable request ID to request state, logs, and response headers."""

    def __init__(self, app, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = getattr(request.state, "request_id", None) or request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid4())

        request.state.request_id = request_id

        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()
        trace_id = f"{span_context.trace_id:032x}" if span_context.is_valid else None

        bind_values = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
        if trace_id:
            bind_values["trace_id"] = trace_id

        tokens = structlog.contextvars.bind_contextvars(**bind_values)

        start_time = time.perf_counter()
        logger.info("request.started")

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception("request.failed", duration_ms=duration_ms)
            structlog.contextvars.reset_contextvars(**tokens)
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers[self.header_name] = request_id
        logger.info(
            "request.completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        structlog.contextvars.reset_contextvars(**tokens)
        return response
