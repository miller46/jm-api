from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus:
    """Task status constants."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreate(BaseModel):
    """Schema for creating a new task."""

    type: str = Field(min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """Schema for task response."""

    id: str
    type: str
    status: str
    payload: dict
    result: dict | None
    error_message: str | None
    attempts: int
    max_attempts: int
    create_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TaskCreateResponse(BaseModel):
    """Schema for task creation response."""

    id: str
    status: str
    create_at: datetime

    model_config = ConfigDict(from_attributes=True)
