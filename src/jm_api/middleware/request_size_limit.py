from __future__ import annotations

import structlog
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)


class RequestBodyTooLargeError(Exception):
    """Raised when request body size exceeds configured limit."""

    def __init__(self, actual_size: int, max_size: int) -> None:
        self.actual_size = actual_size
        self.max_size = max_size
        super().__init__(f"Request body too large: {actual_size} > {max_size}")


class RequestSizeLimitMiddleware:
    """Reject HTTP requests whose body exceeds max_body_bytes."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = 1_048_576) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        headers = Headers(scope=scope)

        content_length = headers.get("content-length")
        if content_length is not None:
            declared_size: int | None
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = None

            if declared_size is not None and declared_size > self.max_body_bytes:
                logger.warning(
                    "request.rejected.payload_too_large",
                    method=method,
                    path=path,
                    content_length=declared_size,
                    max_body_bytes=self.max_body_bytes,
                )
                response = JSONResponse(status_code=413, content={"detail": "Payload Too Large"})
                await response(scope, receive, send)
                return

        bytes_seen = 0

        async def limited_receive() -> Message:
            nonlocal bytes_seen
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                bytes_seen += len(body)
                if bytes_seen > self.max_body_bytes:
                    raise RequestBodyTooLargeError(actual_size=bytes_seen, max_size=self.max_body_bytes)
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLargeError as exc:
            logger.warning(
                "request.rejected.payload_too_large",
                method=method,
                path=path,
                content_length=exc.actual_size,
                max_body_bytes=exc.max_size,
            )
            response = JSONResponse(status_code=413, content={"detail": "Payload Too Large"})
            await response(scope, receive, send)
