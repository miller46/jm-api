from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Task status values."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreate(BaseModel):
    """Schema for creating a new background task."""
    type: str = Field(..., min_length=1, max_length=128)
    payload: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "email.send",
                "payload": {
                    "to": "user@example.com",
                    "subject": "Hello",
                    "body": "Message content"
                }
            }
        }
    )


class TaskResponse(BaseModel):
    """Single task response schema."""
    id: str
    type: str
    status: TaskStatus
    payload: dict | None = None
    result: dict | None = None
    error: str | None = None
    retry_count: int
    created_at: datetime = Field(validation_alias="create_at", serialization_alias="created_at")
    completed_at: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
