from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jm_api.db.base import Base, TimestampedIdBase, utcnow


class TaskStatus(str, PyEnum):
    """Task status enum."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(TimestampedIdBase):
    """Background task model for async job processing."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_type", "type"),
        Index("ix_tasks_create_at", "create_at"),
        Index("ix_tasks_status_create_at", "status", "create_at"),
    )

    type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default_factory=dict)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TaskStatus.QUEUED.value,
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    def is_retryable(self) -> bool:
        """Check if the task can be retried."""
        return self.status == TaskStatus.FAILED.value and self.attempts < self.max_attempts

    def can_process(self) -> bool:
        """Check if the task can be processed."""
        return self.status in (TaskStatus.QUEUED.value, TaskStatus.FAILED.value)
