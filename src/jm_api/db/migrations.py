from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine


class DatabaseMigrationError(RuntimeError):
    """Raised when the database is not at the expected Alembic revision."""



def _alembic_config() -> Config:
    repo_root = Path(__file__).resolve().parents[3]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "alembic"))
    return config


def assert_database_is_up_to_date(engine: Engine) -> None:
    """Fail fast if the running database is not at Alembic head."""
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    expected_head = script.get_current_head()

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_revision = context.get_current_revision()

    if current_revision != expected_head:
        raise DatabaseMigrationError(
            "Database schema is out of date. "
            "Run `alembic upgrade head` before starting the API. "
            f"Current revision: {current_revision!r}, expected: {expected_head!r}."
        )
