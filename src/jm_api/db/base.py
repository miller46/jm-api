from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import DateTime, event
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column

_ID_ALPHABET = string.ascii_lowercase + string.digits


def generate_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(32))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(MappedAsDataclass, DeclarativeBase):
    pass


class TimestampedIdBase(Base):
    __abstract__ = True

    id: Mapped[str] = mapped_column(
        primary_key=True,
        init=False,
        default_factory=generate_id,
    )
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default_factory=utcnow,
    )
    last_update_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default_factory=utcnow,
    )


@event.listens_for(TimestampedIdBase, "before_update", propagate=True)
def _touch_last_update_at(mapper, connection, target) -> None:
    target.last_update_at = utcnow()
