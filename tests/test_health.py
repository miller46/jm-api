from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from jm_api.app import create_app
from jm_api.db.migrations import DatabaseMigrationError


class _FailingEngine:
    @contextmanager
    def connect(self):
        raise SQLAlchemyError("db down")
        yield

    def dispose(self) -> None:
        return None


def test_live_check_returns_ok_and_request_id() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers


def test_healthz_legacy_returns_ok() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_dependency_checks(monkeypatch) -> None:
    app = create_app()

    monkeypatch.setattr(
        "jm_api.api.routes.health.assert_database_is_up_to_date", lambda *args, **kwargs: None
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {
            "database": {"status": "pass"},
            "migrations": {"status": "pass"},
        },
    }


def test_health_returns_503_when_migrations_behind(monkeypatch) -> None:
    app = create_app()

    def _raise(*args, **kwargs) -> None:
        raise DatabaseMigrationError("migrations pending")

    monkeypatch.setattr("jm_api.api.routes.health.assert_database_is_up_to_date", _raise)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "fail"
    assert body["checks"]["database"]["status"] == "pass"
    assert body["checks"]["migrations"]["status"] == "fail"
    assert "migrations pending" in body["checks"]["migrations"]["error"]


def test_meta_returns_deployment_metadata(monkeypatch) -> None:
    app = create_app()

    monkeypatch.setattr(
        "jm_api.app.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "app_version": "1.2.3",
                "git_sha": "abc123def456",
                "deployed_at": "2026-02-23T12:00:00Z",
                "environment": "staging",
            },
        )(),
    )

    with TestClient(app) as client:
        response = client.get("/api/meta")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["version"] == "1.2.3"
    assert body["git_sha"] == "abc123def456"
    assert body["deployed_at"] == "2026-02-23T12:00:00Z"
    assert body["environment"] == "staging"


def test_meta_returns_null_when_not_configured(monkeypatch) -> None:
    app = create_app()

    monkeypatch.setattr(
        "jm_api.app.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "app_version": "0.1.0",
                "git_sha": None,
                "deployed_at": None,
                "environment": "development",
            },
        )(),
    )

    with TestClient(app) as client:
        response = client.get("/api/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "0.1.0"
    assert body["git_sha"] is None
    assert body["deployed_at"] is None
    assert body["environment"] == "development"


def test_ready_returns_503_when_db_connectivity_fails() -> None:
    app = create_app()

    with TestClient(app) as client:
        app.state.db_engine = _FailingEngine()
        response = client.get("/api/v1/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "fail"
    assert body["checks"]["database"]["status"] == "fail"
    assert "db down" in body["checks"]["database"]["error"]
