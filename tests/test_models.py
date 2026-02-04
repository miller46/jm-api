import re
import time
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Session

from jm_api.db.base import Base
from jm_api.models.bot import Bot


def setup_in_memory_db() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_bot_id_generated_and_format() -> None:
    session = setup_in_memory_db()

    bot = Bot(rig_id="rig-123", kill_switch=False, last_run_log="")
    session.add(bot)
    session.commit()
    session.refresh(bot)

    assert isinstance(bot.id, str)
    assert len(bot.id) == 32
    assert re.fullmatch(r"[a-z0-9]{32}", bot.id)


def test_bot_timestamps_create_and_update() -> None:
    session = setup_in_memory_db()

    before_create = datetime.now(timezone.utc).replace(tzinfo=None)
    bot = Bot(rig_id="rig-123", kill_switch=False, last_run_log="")
    session.add(bot)
    session.commit()
    session.refresh(bot)
    after_create = datetime.now(timezone.utc).replace(tzinfo=None)

    assert isinstance(bot.create_at, datetime)
    assert isinstance(bot.last_update_at, datetime)
    # SQLite doesn't preserve timezone, so we verify timestamps are reasonable
    assert before_create <= bot.create_at <= after_create
    assert before_create <= bot.last_update_at <= after_create

    original_updated = bot.last_update_at

    time.sleep(0.01)
    bot.last_run_log = "ran"
    session.add(bot)
    session.commit()
    session.refresh(bot)

    assert bot.last_update_at > original_updated
