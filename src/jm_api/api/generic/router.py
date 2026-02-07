"""Generic read router factory for declarative CRUD endpoints."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jm_api.db.session import get_db
from jm_api.schemas.generic import NotFoundError

from .filters import FilterField, apply_filters, make_filter_dependency


def create_read_router(
    *,
    prefix: str,
    tags: list[str],
    model: type,
    response_schema: type,
    filter_config: list[FilterField],
    resource_name: str,
    id_pattern: str = r"^[a-zA-Z0-9]{32}$",
) -> APIRouter:
    """Create an APIRouter with list and get-by-id endpoints.

    Args:
        prefix: URL prefix (e.g. "/bots").
        tags: OpenAPI tags.
        model: SQLAlchemy model class.
        response_schema: Pydantic response schema.
        filter_config: Declarative filter configuration.
        resource_name: Human-readable name for 404 messages.
        id_pattern: Regex pattern for path ID validation.

    Returns:
        Configured APIRouter with GET "" and GET "/{item_id}" routes.
    """
    router = APIRouter(prefix=prefix, tags=tags)
    filter_dep = make_filter_dependency(filter_config)

    @router.get("")
    def list_items(
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=20, ge=1, le=100),
        filters: Any = Depends(filter_dep),
        db: Session = Depends(get_db),
    ) -> dict:
        filter_values = dataclasses.asdict(filters)

        # Count query
        count_query = apply_filters(
            select(func.count()).select_from(model), model, filter_config, filter_values
        )
        total = db.execute(count_query).scalar() or 0

        # Data query
        data_query = apply_filters(select(model), model, filter_config, filter_values)
        data_query = data_query.order_by(model.create_at.desc(), model.id.desc())
        offset = (page - 1) * per_page
        data_query = data_query.offset(offset).limit(per_page)

        items = db.execute(data_query).scalars().all()
        pages = math.ceil(total / per_page) if total > 0 else 0

        return {
            "items": [response_schema.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @router.get(
        "/{item_id}",
        response_model=response_schema,
        responses={404: {"model": NotFoundError}},
    )
    def get_item(
        item_id: str = Path(pattern=id_pattern),
        db: Session = Depends(get_db),
    ) -> Any:
        item = db.get(model, item_id)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={"message": f"{resource_name} not found", "id": item_id},
            )
        return response_schema.model_validate(item)

    return router
