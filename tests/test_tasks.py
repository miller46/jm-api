"""Tests for the tasks API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from jm_api.api.deps import hash_password
from jm_api.models.task import Task, TaskStatus
from jm_api.models.user import User


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        email="test-tasks@example.com",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(client: TestClient, test_user: User) -> dict[str, str]:
    """Get auth headers for the test user."""
    from jm_api.api.deps import create_access_token

    token = create_access_token(user_id=test_user.id)
    return {"Authorization": f"Bearer {token}"}


class TestCreateTask:
    """Tests for POST /api/v1/tasks."""

    def test_create_task_success(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a task returns the expected response."""
        response = client.post(
            "/api/v1/tasks",
            json={"type": "email.send", "payload": {"to": "test@example.com"}},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert len(data["id"]) == 32
        assert data["status"] == "queued"
        assert "create_at" in data

    def test_create_task_requires_auth(self, client: TestClient) -> None:
        """Test creating a task requires authentication."""
        response = client.post(
            "/api/v1/tasks",
            json={"type": "email.send", "payload": {}},
        )
        assert response.status_code == 401

    def test_create_task_invalid_type(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test creating a task with invalid type fails."""
        response = client.post(
            "/api/v1/tasks",
            json={"type": "", "payload": {}},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_task_default_payload(
        self, client: TestClient, auth_headers: dict[str, str], db_session: Session
    ) -> None:
        """Test creating a task with default empty payload."""
        response = client.post(
            "/api/v1/tasks",
            json={"type": "test.task"},
            headers=auth_headers,
        )
        assert response.status_code == 201


class TestGetTask:
    """Tests for GET /api/v1/tasks/:id."""

    def test_get_task_success(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        test_user: User,
    ) -> None:
        """Test getting a task returns the expected response."""
        # Create a task
        task = Task(
            type="email.send",
            payload={"to": "test@example.com"},
            status=TaskStatus.QUEUED,
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.get(f"/api/v1/tasks/{task.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task.id
        assert data["type"] == "email.send"
        assert data["status"] == "queued"
        assert data["payload"] == {"to": "test@example.com"}
        assert data["attempts"] == 0
        assert data["max_attempts"] == 3

    def test_get_task_completed(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        test_user: User,
    ) -> None:
        """Test getting a completed task includes result."""
        from datetime import datetime, timezone

        task = Task(
            type="email.send",
            payload={"to": "test@example.com"},
            status=TaskStatus.COMPLETED,
            result={"sent": True},
            attempts=1,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.get(f"/api/v1/tasks/{task.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"] == {"sent": True}
        assert data["started_at"] is not None
        assert data["completed_at"] is not None

    def test_get_task_failed(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        test_user: User,
    ) -> None:
        """Test getting a failed task includes error message."""
        task = Task(
            type="email.send",
            payload={"to": "test@example.com"},
            status=TaskStatus.FAILED,
            error_message="SMTP connection failed",
            attempts=3,
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.get(f"/api/v1/tasks/{task.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "SMTP connection failed"

    def test_get_task_not_found(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test getting a non-existent task returns 404."""
        response = client.get(
            "/api/v1/tasks/abc123def456abc123def456abc123de",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_task_requires_auth(self, client: TestClient) -> None:
        """Test getting a task requires authentication."""
        response = client.get("/api/v1/tasks/abc123def456abc123def456abc123de")
        assert response.status_code == 401

    def test_get_task_invalid_id_format(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test getting a task with invalid ID format returns 422."""
        response = client.get("/api/v1/tasks/invalid-id", headers=auth_headers)
        assert response.status_code == 422
