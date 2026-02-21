from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jm_api.db.base import TimestampedIdBase


class Bot(TimestampedIdBase):
    __tablename__ = "bots"
    __table_args__ = (
        Index("ix_bots_rig_id", "rig_id"),
        Index("ix_bots_kill_switch", "kill_switch"),
        Index("ix_bots_create_at", "create_at"),
        Index("ix_bots_last_update_at", "last_update_at"),
        Index("ix_bots_last_run_at", "last_run_at"),
        Index("ix_bots_rig_id_kill_switch", "rig_id", "kill_switch"),
        Index("ix_bots_kill_switch_last_run_at", "kill_switch", "last_run_at"),
    )

    rig_id: Mapped[str] = mapped_column(String(128), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_log: Mapped[str | None] = mapped_column(Text, default="")
