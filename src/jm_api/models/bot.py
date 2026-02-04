from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jm_api.db.base import TimestampedIdBase


class Bot(TimestampedIdBase):
    __tablename__ = "bots"

    rig_id: Mapped[str] = mapped_column(String(128), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_log: Mapped[str | None] = mapped_column(Text, default="")
