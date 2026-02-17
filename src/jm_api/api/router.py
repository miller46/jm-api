from __future__ import annotations

from fastapi import APIRouter

from jm_api.api.routes import auth, bots, health

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(bots.router)
