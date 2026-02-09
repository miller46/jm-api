"""Declarative filter system for generic CRUD endpoints."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy.sql import Select


class FilterType(Enum):
    """Supported filter types."""

    EXACT = "exact"
    ILIKE = "ilike"
    DATE_RANGE = "date_range"


@dataclasses.dataclass(frozen=True)
class FilterField:
    """Declarative filter field configuration.

    Args:
        column_name: SQLAlchemy model column name.
        filter_type: How to filter (EXACT, ILIKE, DATE_RANGE).
        param_name: Query parameter name. Defaults to column_name.
        python_type: Python type for OpenAPI schema. Default str.
    """

    column_name: str
    filter_type: FilterType
    param_name: str | None = None
    python_type: type = str

    @property
    def effective_param_name(self) -> str:
        return self.param_name if self.param_name is not None else self.column_name


def apply_filters(
    query: Select,
    model: type,
    filter_config: list[FilterField],
    filter_values: dict[str, Any],
) -> Select:
    """Apply declarative filters to a SQLAlchemy query.

    Args:
        query: Base SELECT query.
        model: SQLAlchemy model class.
        filter_config: List of FilterField declarations.
        filter_values: Dict of param_name -> value from request.

    Returns:
        Query with WHERE clauses applied.
    """
    for field in filter_config:
        if field.filter_type == FilterType.EXACT:
            value = filter_values.get(field.effective_param_name)
            if value is not None:
                column = getattr(model, field.column_name)
                query = query.where(column == value)

        elif field.filter_type == FilterType.ILIKE:
            value = filter_values.get(field.effective_param_name)
            if value is not None:
                column = getattr(model, field.column_name)
                # Escape SQL wildcards to prevent injection
                escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                query = query.where(column.ilike(f"%{escaped}%", escape="\\"))

        elif field.filter_type == FilterType.DATE_RANGE:
            param = field.effective_param_name
            after_value = filter_values.get(f"{param}_after")
            before_value = filter_values.get(f"{param}_before")
            column = getattr(model, field.column_name)
            if after_value is not None:
                query = query.where(column >= after_value)
            if before_value is not None:
                query = query.where(column <= before_value)

    return query


def make_filter_dependency(
    filter_config: list[FilterField],
    resource_name: str = "",
) -> type:
    """Create a dataclass suitable for FastAPI Depends() from filter config.

    FastAPI introspects the class fields as Query parameters.

    Args:
        filter_config: List of FilterField declarations.
        resource_name: Resource name for unique class naming in OpenAPI schema.

    Returns:
        A dataclass type with Optional fields for each filter parameter.
    """
    fields: list[tuple[str, type, dataclasses.Field]] = []

    for field in filter_config:
        if field.filter_type == FilterType.DATE_RANGE:
            param = field.effective_param_name
            fields.append(
                (f"{param}_after", datetime | None, dataclasses.field(default=None))
            )
            fields.append(
                (f"{param}_before", datetime | None, dataclasses.field(default=None))
            )
        elif field.filter_type == FilterType.EXACT:
            fields.append(
                (
                    field.effective_param_name,
                    field.python_type | None,
                    dataclasses.field(default=None),
                )
            )
        elif field.filter_type == FilterType.ILIKE:
            fields.append(
                (
                    field.effective_param_name,
                    str | None,
                    dataclasses.field(default=None),
                )
            )

    class_name = f"{resource_name}FilterParams" if resource_name else "FilterParams"
    return dataclasses.make_dataclass(class_name, fields)
