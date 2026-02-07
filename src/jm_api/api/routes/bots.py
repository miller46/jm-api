from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from jm_api.db.session import get_db
from jm_api.models.bot import Bot
from jm_api.schemas.bot import BotListResponse, BotNotFoundError, BotResponse

router = APIRouter(prefix="/bots", tags=["bots"])


@dataclass
class BotFilters:
    """Filter parameters for bot queries."""

    rig_id: str | None = None
    kill_switch: bool | None = None
    log_search: str | None = None
    create_at_after: datetime | None = None
    create_at_before: datetime | None = None
    last_update_at_after: datetime | None = None
    last_update_at_before: datetime | None = None
    last_run_at_after: datetime | None = None
    last_run_at_before: datetime | None = None


def _apply_bot_filters(query: Select, filters: BotFilters) -> Select:
    """Apply filters to a bot query.

    Used by both data and count queries to ensure consistent filtering.
    """
    if filters.rig_id is not None:
        query = query.where(Bot.rig_id == filters.rig_id)
    if filters.kill_switch is not None:
        query = query.where(Bot.kill_switch == filters.kill_switch)
    if filters.log_search is not None:
        # Escape SQL wildcards to prevent injection
        escaped = filters.log_search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Bot.last_run_log.ilike(f"%{escaped}%", escape="\\"))
    if filters.create_at_after is not None:
        query = query.where(Bot.create_at >= filters.create_at_after)
    if filters.create_at_before is not None:
        query = query.where(Bot.create_at <= filters.create_at_before)
    if filters.last_update_at_after is not None:
        query = query.where(Bot.last_update_at >= filters.last_update_at_after)
    if filters.last_update_at_before is not None:
        query = query.where(Bot.last_update_at <= filters.last_update_at_before)
    if filters.last_run_at_after is not None:
        query = query.where(Bot.last_run_at >= filters.last_run_at_after)
    if filters.last_run_at_before is not None:
        query = query.where(Bot.last_run_at <= filters.last_run_at_before)
    return query


@router.get("", response_model=BotListResponse)
def list_bots(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    rig_id: str | None = Query(default=None),
    kill_switch: bool | None = Query(default=None),
    log_search: str | None = Query(default=None),
    create_at_after: datetime | None = Query(default=None),
    create_at_before: datetime | None = Query(default=None),
    last_update_at_after: datetime | None = Query(default=None),
    last_update_at_before: datetime | None = Query(default=None),
    last_run_at_after: datetime | None = Query(default=None),
    last_run_at_before: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BotListResponse:
    """List all bots with filtering, pagination, and sorting."""
    filters = BotFilters(
        rig_id=rig_id,
        kill_switch=kill_switch,
        log_search=log_search,
        create_at_after=create_at_after,
        create_at_before=create_at_before,
        last_update_at_after=last_update_at_after,
        last_update_at_before=last_update_at_before,
        last_run_at_after=last_run_at_after,
        last_run_at_before=last_run_at_before,
    )

    # Get total count using direct WHERE clauses (more efficient than subquery)
    count_query = _apply_bot_filters(
        select(func.count()).select_from(Bot), filters
    )
    total = db.execute(count_query).scalar() or 0

    # Build data query with same filters
    data_query = _apply_bot_filters(select(Bot), filters)

    # Apply sorting and pagination (secondary sort by id for deterministic order)
    data_query = data_query.order_by(Bot.create_at.desc(), Bot.id.desc())
    offset = (page - 1) * per_page
    data_query = data_query.offset(offset).limit(per_page)

    # Execute query
    bots = db.execute(data_query).scalars().all()

    # Calculate pages
    pages = math.ceil(total / per_page) if total > 0 else 0

    return BotListResponse(
        items=[BotResponse.model_validate(bot) for bot in bots],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get(
    "/{bot_id}",
    response_model=BotResponse,
    responses={404: {"model": BotNotFoundError}},
)
def get_bot(
    bot_id: str = Path(pattern=r"^[a-zA-Z0-9]{32}$"),
    db: Session = Depends(get_db),
) -> BotResponse:
    """Retrieve a single bot by ID."""
    bot = db.get(Bot, bot_id)
    if bot is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "Bot not found", "id": bot_id},
        )
    return BotResponse.model_validate(bot)
