from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid4())

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[self.header_name] = request_id
        return response
