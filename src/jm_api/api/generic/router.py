"""Generic router factories for declarative CRUD endpoints."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.status import HTTP_201_CREATED, HTTP_409_CONFLICT

from jm_api.db.session import get_db
from jm_api.schemas.generic import ListResponse, NotFoundError

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
    sort_columns: list[tuple[str, str]] | None = None,
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
        sort_columns: List of (column_name, direction) tuples for ORDER BY.
            Defaults to [("create_at", "desc"), ("id", "desc")].

    Returns:
        Configured APIRouter with GET "" and GET "/{item_id}" routes.
    """
    if sort_columns is None:
        sort_columns = [("create_at", "desc"), ("id", "desc")]

    router = APIRouter(prefix=prefix, tags=tags)
    filter_dep = make_filter_dependency(filter_config, resource_name=resource_name)
    list_response_model = ListResponse[response_schema]
    name_lower = resource_name.lower()

    @router.get("", response_model=list_response_model, name=f"list_{name_lower}s")
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

        # Apply sort order
        order_clauses = []
        for col_name, direction in sort_columns:
            column = getattr(model, col_name)
            order_clauses.append(column.desc() if direction == "desc" else column.asc())
        data_query = data_query.order_by(*order_clauses)

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
        name=f"get_{name_lower}",
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

    # Rename functions for unique OpenAPI operation_ids across multiple routers
    list_items.__name__ = f"list_{name_lower}s"
    get_item.__name__ = f"get_{name_lower}"

    return router


def create_create_router(
    *,
    prefix: str,
    tags: list[str],
    model: type,
    response_schema: type,
    create_schema: type,
    resource_name: str,
) -> APIRouter:
    """Create an APIRouter with a POST endpoint for creating records.

    Args:
        prefix: URL prefix (e.g. "/bots").
        tags: OpenAPI tags.
        model: SQLAlchemy model class.
        response_schema: Pydantic response schema.
        create_schema: Pydantic schema for the request body.
        resource_name: Human-readable name for operation naming.

    Returns:
        Configured APIRouter with POST "" route.
    """
    router = APIRouter(prefix=prefix, tags=tags)
    name_lower = resource_name.lower()

    # Build endpoint function with proper annotations for FastAPI.
    # We can't use `payload: create_schema` directly because
    # `from __future__ import annotations` turns it into a string literal.
    # Instead, we set __annotations__ manually on the function.
    def create_item(payload, *, db: Session = Depends(get_db)) -> Any:
        item = model(**payload.model_dump())
        db.add(item)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Record conflicts with an existing entry: {exc.orig}",
            ) from exc
        db.refresh(item)
        return response_schema.model_validate(item)

    create_item.__annotations__["payload"] = create_schema
    create_item.__name__ = f"create_{name_lower}"

    router.add_api_route(
        "",
        create_item,
        methods=["POST"],
        response_model=response_schema,
        status_code=HTTP_201_CREATED,
        name=f"create_{name_lower}",
    )

    return router
