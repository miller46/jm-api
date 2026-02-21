"""Bot CRUD endpoints — declarative config using the generic CRUD layer."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from jm_api.api.deps import ADMIN_ONLY

from jm_api.api.generic import (
    create_create_router,
    create_delete_router,
    create_read_router,
    create_update_router,
)
from jm_api.api.generic.filters import FilterField, FilterType
from jm_api.models.bot import Bot
from jm_api.schemas.bot import BotCreate, BotResponse, BotUpdate

BOT_FILTERS = [
    FilterField("rig_id", FilterType.EXACT),
    FilterField("kill_switch", FilterType.EXACT, python_type=bool),
    FilterField("last_run_log", FilterType.ILIKE, param_name="log_search"),
    FilterField("create_at", FilterType.DATE_RANGE),
    FilterField("last_update_at", FilterType.DATE_RANGE),
    FilterField("last_run_at", FilterType.DATE_RANGE),
]

_read_router = create_read_router(
    prefix="/bots",
    tags=["bots"],
    model=Bot,
    response_schema=BotResponse,
    filter_config=BOT_FILTERS,
    resource_name="Bot",
)

_create_router = create_create_router(
    prefix="/bots",
    tags=["bots"],
    model=Bot,
    response_schema=BotResponse,
    create_schema=BotCreate,
    resource_name="Bot",
)

_update_router = create_update_router(
    prefix="/bots",
    tags=["bots"],
    model=Bot,
    response_schema=BotResponse,
    update_schema=BotUpdate,
    resource_name="Bot",
)

_delete_router = create_delete_router(
    prefix="/bots",
    tags=["bots"],
    model=Bot,
    resource_name="Bot",
)

router = APIRouter()
router.include_router(_read_router)

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = True) -> tuple[bool, bool]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default, False

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True, True
    if normalized in {"0", "false", "no", "off"}:
        return False, True

    logger.warning(
        "Invalid value for %s=%r; defaulting to %s",
        name,
        raw_value,
        default,
    )
    return default, True


_bots_write_admin_only, _bots_write_admin_only_explicit = _env_flag(
    "JM_API_BOTS_WRITE_ADMIN_ONLY",
    default=True,
)
if _bots_write_admin_only_explicit and not _bots_write_admin_only:
    logger.warning(
        "Bot write protection is DISABLED via JM_API_BOTS_WRITE_ADMIN_ONLY=false; "
        "write endpoints are not admin-restricted."
    )

_write_dependencies = ADMIN_ONLY if _bots_write_admin_only else None

router.include_router(_create_router, dependencies=_write_dependencies)
router.include_router(_update_router, dependencies=_write_dependencies)
router.include_router(_delete_router, dependencies=_write_dependencies)
