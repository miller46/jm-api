from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from jm_api.api.router import router as api_router
from jm_api.core.config import get_settings
from jm_api.core.lifespan import lifespan
from jm_api.core.logging import configure_logging
from jm_api.middleware.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        openapi_url=settings.openapi_url if settings.docs_enabled else None,
        docs_url=settings.docs_url if settings.docs_enabled else None,
        redoc_url=settings.redoc_url if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware, header_name=settings.request_id_header)

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

    return app
