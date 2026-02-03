from __future__ import annotations

from fastapi import APIRouter

from jm_api.api.routes import health

router = APIRouter()
router.include_router(health.router)
