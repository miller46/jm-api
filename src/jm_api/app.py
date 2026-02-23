from __future__ import annotations

from pathlib import Path
import re
from time import time

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from jm_api.api.router import router as api_router
from jm_api.api.routes import limiter
from jm_api.core.config import get_settings
from jm_api.core.lifespan import lifespan
from jm_api.core.logging import configure_logging
from jm_api.core.observability import install_metrics, install_tracing
from jm_api.middleware.graceful_shutdown import GracefulShutdownMiddleware
from jm_api.middleware.request_id import RequestIdMiddleware
from jm_api.middleware.security_headers import SecurityHeadersMiddleware

_STATIC_DIR = Path(__file__).resolve().parent / "static"
logger = structlog.get_logger(__name__)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    logger.warning(
        "rate_limit.exceeded",
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
    )

    headers = dict(getattr(exc, "headers", {}) or {})
    if "Retry-After" not in headers:
        headers["Retry-After"] = "60"

    raw_detail = str(getattr(exc, "detail", ""))
    match = re.search(r"(\d+)\s+per\s+(\d+)\s+(second|minute|hour|day|month)", raw_detail)
    if match:
        limit = match.group(1)
        window = int(match.group(2))
        unit = match.group(3)
        seconds_per_unit = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "month": 2592000}
        retry_after = str(window * seconds_per_unit[unit])
        headers.setdefault("Retry-After", retry_after)
        headers.setdefault("X-RateLimit-Limit", limit)
    headers.setdefault("X-RateLimit-Remaining", "0")
    headers.setdefault("X-RateLimit-Reset", str(int(time()) + int(headers["Retry-After"])))

    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
        headers=headers,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        json_logs=settings.log_json,
        sample_rate=settings.log_sample_rate,
    )

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        openapi_url=settings.openapi_url if settings.docs_enabled else None,
        docs_url=settings.docs_url if settings.docs_enabled else None,
        redoc_url=settings.redoc_url if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    install_tracing(app, settings)
    install_metrics(app, settings)

    # Add graceful shutdown middleware first to catch requests during shutdown
    app.add_middleware(GracefulShutdownMiddleware)

    # Add rate limiting
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    app.add_middleware(RequestIdMiddleware, header_name=settings.request_id_header)

    if settings.security_headers_enabled:
        app.add_middleware(
            SecurityHeadersMiddleware,
            x_content_type_options=settings.security_header_x_content_type_options,
            x_frame_options=settings.security_header_x_frame_options,
            strict_transport_security=settings.security_header_hsts_value,
            admin_csp=settings.security_header_admin_csp,
        )

    if settings.allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    if settings.allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allow_origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=settings.cors_allow_methods,
            allow_headers=settings.cors_allow_headers,
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # Deployment metadata endpoint at /api/meta (outside v1 prefix)
    @app.get("/api/meta", tags=["health"])
    def deployment_metadata() -> dict[str, str | None]:
        """Return deployment metadata for verifying live code version."""
        s = get_settings()
        return {
            "version": s.app_version,
            "git_sha": s.git_sha,
            "deployed_at": s.deployed_at,
            "environment": s.environment,
        }

    app.mount("/admin", StaticFiles(directory=str(_STATIC_DIR)), name="admin")

    return app
