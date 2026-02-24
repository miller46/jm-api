from jm_api.db.session import _build_engine_kwargs


def test_build_engine_kwargs_for_postgres_sets_statement_timeout() -> None:
    kwargs = _build_engine_kwargs("postgresql://user:pass@localhost/db")

    assert kwargs["connect_args"] == {"options": "-c statement_timeout=30000"}
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 300


def test_build_engine_kwargs_for_sqlite_sets_check_same_thread_only() -> None:
    kwargs = _build_engine_kwargs("sqlite:///:memory:")

    assert kwargs == {"connect_args": {"check_same_thread": False}}
