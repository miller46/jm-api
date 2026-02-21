from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jm_api.db.base import Base, TimestampedIdBase, utcnow


class Webhook(TimestampedIdBase):
    __tablename__ = "webhooks"
    __table_args__ = (
        Index("ix_webhooks_user_id", "user_id"),
        Index("ix_webhooks_is_active", "is_active"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default_factory=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WebhookDeliveryLog(Base):
    __tablename__ = "webhook_delivery_logs"
    __table_args__ = (
        Index("ix_webhook_delivery_logs_webhook_id", "webhook_id"),
        Index("ix_webhook_delivery_logs_event_type", "event_type"),
        Index("ix_webhook_delivery_logs_create_at", "create_at"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    webhook_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    create_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), init=False, default_factory=utcnow)
