from __future__ import annotations

import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from jm_api.db.session import get_db
from jm_api.models.bot import Bot
from jm_api.schemas.bot import BotListResponse, BotNotFoundError, BotResponse

router = APIRouter(prefix="/bots", tags=["bots"])


@router.get("", response_model=BotListResponse)
def list_bots(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1),
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
    # Cap per_page at 100
    per_page = min(per_page, 100)

    query = select(Bot)

    # Apply filters (AND logic)
    if rig_id is not None:
        query = query.where(Bot.rig_id == rig_id)
    if kill_switch is not None:
        query = query.where(Bot.kill_switch == kill_switch)
    if log_search is not None:
        # Escape SQL wildcards to prevent injection
        escaped = log_search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Bot.last_run_log.ilike(f"%{escaped}%", escape="\\"))
    if create_at_after is not None:
        query = query.where(Bot.create_at >= create_at_after)
    if create_at_before is not None:
        query = query.where(Bot.create_at <= create_at_before)
    if last_update_at_after is not None:
        query = query.where(Bot.last_update_at >= last_update_at_after)
    if last_update_at_before is not None:
        query = query.where(Bot.last_update_at <= last_update_at_before)
    if last_run_at_after is not None:
        query = query.where(Bot.last_run_at >= last_run_at_after)
    if last_run_at_before is not None:
        query = query.where(Bot.last_run_at <= last_run_at_before)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    # Apply sorting and pagination (secondary sort by id for deterministic order)
    query = query.order_by(Bot.create_at.desc(), Bot.id.desc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # Execute query
    bots = db.execute(query).scalars().all()

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
def get_bot(bot_id: str, db: Session = Depends(get_db)) -> BotResponse:
    """Retrieve a single bot by ID."""
    bot = db.get(Bot, bot_id)
    if bot is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Bot not found", "id": bot_id},
        )
    return BotResponse.model_validate(bot)
