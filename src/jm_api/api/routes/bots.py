"""Bot read endpoints — declarative config using the generic CRUD layer."""

from __future__ import annotations

from jm_api.api.generic import create_read_router
from jm_api.api.generic.filters import FilterField, FilterType
from jm_api.models.bot import Bot
from jm_api.schemas.bot import BotResponse

BOT_FILTERS = [
    FilterField("rig_id", FilterType.EXACT),
    FilterField("kill_switch", FilterType.EXACT, python_type=bool),
    FilterField("last_run_log", FilterType.ILIKE, param_name="log_search"),
    FilterField("create_at", FilterType.DATE_RANGE),
    FilterField("last_update_at", FilterType.DATE_RANGE),
    FilterField("last_run_at", FilterType.DATE_RANGE),
]

router = create_read_router(
    prefix="/bots",
    tags=["bots"],
    model=Bot,
    response_schema=BotResponse,
    filter_config=BOT_FILTERS,
    resource_name="Bot",
)
