from __future__ import annotations

from fastapi import APIRouter

from jm_api.api.routes import admin, auth, bots, health, webhooks

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(bots.router)
router.include_router(webhooks.router)
router.include_router(admin.router)
