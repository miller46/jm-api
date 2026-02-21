from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


SUPPORTED_WEBHOOK_EVENT_TYPES = {
    "bot.created",
    "bot.updated",
    "bot.deleted",
    "bot.ran",
}


class WebhookCreate(BaseModel):
    target_url: str = Field(min_length=1, max_length=1024)
    event_types: list[str] = Field(min_length=1)
    secret: str = Field(min_length=8, max_length=255)


class WebhookUpdate(BaseModel):
    target_url: str | None = Field(default=None, min_length=1, max_length=1024)
    event_types: list[str] | None = None
    secret: str | None = Field(default=None, min_length=8, max_length=255)
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: str
    user_id: str
    target_url: str
    event_types: list[str]
    is_active: bool
    create_at: datetime
    last_update_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryLogResponse(BaseModel):
    id: str
    webhook_id: str
    event_id: str
    event_type: str
    success: bool
    attempts: int
    status_code: int | None
    response_body: str | None
    error_message: str | None
    create_at: datetime

    model_config = ConfigDict(from_attributes=True)
