from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, BaseModel, field_validator

from jm_api.schemas.generic import ListResponse


class BotCreate(BaseModel):
    """Schema for creating a new bot. Only user-editable fields."""

    rig_id: str
    kill_switch: bool = False
    last_run_log: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rig_id": "rig-001",
                "kill_switch": False,
                "last_run_log": None,
            }
        },
    )


class BotUpdate(BaseModel):
    """Schema for updating a bot. All fields optional for partial updates.

    Non-nullable fields (rig_id, kill_switch) reject explicit null values
    to prevent setting DB columns to NULL in violation of application invariants.
    """

    rig_id: str | None = None
    kill_switch: bool | None = None
    last_run_log: str | None = None

    @field_validator("rig_id", "kill_switch", mode="before")
    @classmethod
    def reject_none_for_non_nullable(cls, v: object, info) -> object:  # noqa: ANN401
        """Reject explicit null for non-nullable fields."""
        if v is None:
            msg = f"{info.field_name} cannot be null"
            raise ValueError(msg)
        return v


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


class BotListResponse(ListResponse[BotResponse]):
    """Paginated list of bots response schema."""

    pass
