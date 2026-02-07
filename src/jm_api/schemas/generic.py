"""Generic response schemas for reusable CRUD endpoints."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ListResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


class NotFoundError(BaseModel):
    """Standard 404 error response."""

    message: str
    id: str
