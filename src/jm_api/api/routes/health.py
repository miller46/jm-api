from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette import status
from starlette.responses import JSONResponse

from jm_api.api.routes.admin import is_health_break_triggered
from jm_api.db.migrations import DatabaseMigrationError, assert_database_is_up_to_date

router = APIRouter(tags=["health"])


@router.get("/live")
def liveness_check() -> dict[str, str]:
    """Basic liveness probe: process is up and serving requests."""
    if is_health_break_triggered():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "fail", "error": "artificial health check failure triggered"},
        )
    return {"status": "ok"}


@router.get("/health")
def health_check(request: Request) -> JSONResponse:
    """Deep health check for dependency state."""
    if is_health_break_triggered():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "fail", "error": "artificial health check failure triggered"},
        )
    payload, code = _build_deep_health_payload(request)
    return JSONResponse(status_code=code, content=payload)


@router.get("/ready")
def readiness_check(request: Request) -> JSONResponse:
    """Readiness probe for orchestration systems."""
    if is_health_break_triggered():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "fail", "error": "artificial health check failure triggered"},
        )
    payload, code = _build_deep_health_payload(request)
    return JSONResponse(status_code=code, content=payload)


@router.get("/healthz")
def healthz_backwards_compat() -> dict[str, str]:
    """Legacy health endpoint maintained for compatibility."""
    return {"status": "ok"}


def _build_deep_health_payload(request: Request) -> tuple[dict[str, Any], int]:
    engine = request.app.state.db_engine

    checks: dict[str, dict[str, Any]] = {
        "database": {"status": "pass"},
        "migrations": {"status": "pass"},
    }

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        checks["database"] = {
            "status": "fail",
            "error": f"{exc.__class__.__name__}: {exc}",
        }
        return {
            "status": "fail",
            "checks": checks,
        }, status.HTTP_503_SERVICE_UNAVAILABLE

    try:
        assert_database_is_up_to_date(engine)
    except DatabaseMigrationError as exc:
        checks["migrations"] = {"status": "fail", "error": str(exc)}
        return {
            "status": "fail",
            "checks": checks,
        }, status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok",
        "checks": checks,
    }, status.HTTP_200_OK
