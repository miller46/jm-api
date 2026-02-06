from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BotResponse(BaseModel):
    """Single bot response schema."""

    id: str
    rig_id: str
    last_run_at: datetime | None
    kill_switch: bool
    last_run_log: str | None
    create_at: datetime
    last_update_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
                "rig_id": "rig-001",
                "last_run_at": "2024-01-15T10:30:00Z",
                "kill_switch": False,
                "last_run_log": "Bot executed successfully",
                "create_at": "2024-01-01T00:00:00Z",
                "last_update_at": "2024-01-15T10:30:00Z",
            }
        },
    )


class BotListResponse(BaseModel):
    """Paginated list of bots response schema."""

    items: list[BotResponse]
    total: int
    page: int
    per_page: int
    pages: int


class BotNotFoundError(BaseModel):
    """Error response when bot is not found."""

    message: str = "Bot not found"
    id: str
