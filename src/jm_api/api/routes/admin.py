"""Admin routes for system testing and management."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.responses import JSONResponse

from jm_api.api.deps import require_admin
from jm_api.core.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])
logger = structlog.get_logger(__name__)

# In-memory flag for artificial health check failure
# Resets on application restart as per requirements
_health_break_triggered: bool = False


def is_health_break_triggered() -> bool:
    """Check if health break is currently triggered."""
    return _health_break_triggered


def set_health_break_triggered(value: bool) -> None:
    """Set the health break trigger state."""
    global _health_break_triggered
    _health_break_triggered = value


@router.post("/break", response_model=dict[str, str])
def trigger_health_break(
    request: Request,
    current_admin: dict = Depends(require_admin),
) -> dict[str, str]:
    """Trigger artificial health check failure for testing.
    
    Requires admin authentication. Sets an in-memory flag that causes
    health endpoints to return 500 errors until reset or app restart.
    """
    global _health_break_triggered
    _health_break_triggered = True
    
    logger.warning(
        "admin.health_break.triggered",
        admin_user_id=str(current_admin.id) if hasattr(current_admin, 'id') else None,
        request_id=getattr(request.state, "request_id", None),
    )
    
    return {"status": "health break triggered"}


@router.post("/break/reset", response_model=dict[str, str])
def reset_health_break(
    request: Request,
    current_admin: dict = Depends(require_admin),
) -> dict[str, str]:
    """Reset artificial health check failure.
    
    Requires admin authentication. Clears the in-memory flag,
    restoring normal health check behavior.
    """
    global _health_break_triggered
    _health_break_triggered = False
    
    logger.info(
        "admin.health_break.reset",
        admin_user_id=str(current_admin.id) if hasattr(current_admin, 'id') else None,
        request_id=getattr(request.state, "request_id", None),
    )
    
    return {"status": "health break reset"}


@router.get("/break/status", response_model=dict[str, bool])
def get_health_break_status(
    current_admin: dict = Depends(require_admin),
) -> dict[str, bool]:
    """Get current health break status.
    
    Requires admin authentication. Returns whether the artificial
    health check failure is currently active.
    """
    return {"triggered": _health_break_triggered}
