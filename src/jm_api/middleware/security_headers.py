from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline security headers to all responses.

    A stricter CSP is only applied to /admin endpoints.
    """

    def __init__(
        self,
        app,
        *,
        x_content_type_options: str,
        x_frame_options: str,
        strict_transport_security: str,
        admin_csp: str,
    ) -> None:
        super().__init__(app)
        self._x_content_type_options = x_content_type_options
        self._x_frame_options = x_frame_options
        self._strict_transport_security = strict_transport_security
        self._admin_csp = admin_csp

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", self._x_content_type_options)
        response.headers.setdefault("X-Frame-Options", self._x_frame_options)
        response.headers.setdefault("Strict-Transport-Security", self._strict_transport_security)

        if request.url.path.startswith("/admin"):
            response.headers.setdefault("Content-Security-Policy", self._admin_csp)

        return response
