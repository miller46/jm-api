"""Middleware for graceful shutdown request handling.

This middleware tracks active requests and rejects new requests
when the application is shutting down.
"""

from __future__ import annotations

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from jm_api.core.shutdown import (
    decrement_active_requests,
    increment_active_requests,
    is_shutting_down,
)

logger = structlog.get_logger(__name__)


class GracefulShutdownMiddleware(BaseHTTPMiddleware):
    """Middleware to handle graceful shutdown.
    
    - Tracks active requests for proper connection draining
    - Rejects new requests with 503 Service Unavailable when shutting down
    - Ensures proper cleanup even on exceptions
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check if we're shutting down - reject new requests
        if is_shutting_down():
            logger.warning(
                "shutdown.request_rejected",
                path=request.url.path,
                method=request.method,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service is shutting down. Please retry later."
                },
                headers={"Retry-After": "10"},
            )

        # Track active request
        increment_active_requests()
        
        try:
            response = await call_next(request)
            return response
        finally:
            # Always decrement, even if an exception occurred
            decrement_active_requests()
