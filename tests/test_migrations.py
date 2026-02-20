from __future__ import annotations

import pytest
import sqlalchemy as sa

from jm_api.db.migrations import DatabaseMigrationError, assert_database_is_up_to_date


class _FakeScriptDirectory:
    def get_current_head(self) -> str:
        return "head_rev"


def test_assert_database_is_up_to_date_passes_when_head(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")

    monkeypatch.setattr(
        "jm_api.db.migrations.ScriptDirectory.from_config",
        lambda config: _FakeScriptDirectory(),
    )

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES ('head_rev')")

    assert_database_is_up_to_date(engine)


def test_assert_database_is_up_to_date_raises_when_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")

    monkeypatch.setattr(
        "jm_api.db.migrations.ScriptDirectory.from_config",
        lambda config: _FakeScriptDirectory(),
    )

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES ('old_rev')")

    with pytest.raises(DatabaseMigrationError, match="out of date"):
        assert_database_is_up_to_date(engine)
