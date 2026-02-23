"""Tests for admin break endpoint (issue #98).

Tests cover:
  1. POST /api/v1/admin/break - triggers health check failure
  2. POST /api/v1/admin/break/reset - resets health check failure
  3. GET /api/v1/admin/break/status - gets current break status
  4. Health endpoints return 500 when break is triggered
  5. Admin-only access control
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jm_api.api.routes.admin import set_health_break_triggered


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def reset_break_state():
    """Reset break state before each test."""
    set_health_break_triggered(False)
    yield
    set_health_break_triggered(False)


# ===================================================================
# Authentication/Authorization Tests
# ===================================================================

class TestAdminBreakAuth:
    """Verify admin-only access control."""

    def test_break_requires_authentication(self, client: TestClient) -> None:
        """POST /api/v1/admin/break returns 401 without auth."""
        response = client.post("/api/v1/admin/break")
        assert response.status_code == 401

    def test_break_reset_requires_authentication(self, client: TestClient) -> None:
        """POST /api/v1/admin/break/reset returns 401 without auth."""
        response = client.post("/api/v1/admin/break/reset")
        assert response.status_code == 401

    def test_break_status_requires_authentication(self, client: TestClient) -> None:
        """GET /api/v1/admin/break/status returns 401 without auth."""
        response = client.get("/api/v1/admin/break/status")
        assert response.status_code == 401

    def test_break_requires_admin_privileges(self, client: TestClient, user_factory) -> None:
        """POST /api/v1/admin/break returns 403 for non-admin user."""
        user = user_factory(is_admin=False)
        token = _get_access_token(client, user.email, "password123")
        
        response = client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_break_reset_requires_admin_privileges(self, client: TestClient, user_factory) -> None:
        """POST /api/v1/admin/break/reset returns 403 for non-admin user."""
        user = user_factory(is_admin=False)
        token = _get_access_token(client, user.email, "password123")
        
        response = client.post(
            "/api/v1/admin/break/reset",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_break_status_requires_admin_privileges(self, client: TestClient, user_factory) -> None:
        """GET /api/v1/admin/break/status returns 403 for non-admin user."""
        user = user_factory(is_admin=False)
        token = _get_access_token(client, user.email, "password123")
        
        response = client.get(
            "/api/v1/admin/break/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ===================================================================
# Admin Break Functionality Tests
# ===================================================================

class TestAdminBreakTrigger:
    """Verify break trigger functionality."""

    def test_admin_can_trigger_break(self, client: TestClient, admin_user_factory) -> None:
        """Admin can successfully trigger health break."""
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        response = client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "health break triggered"}

    def test_break_causes_health_to_return_500(self, client: TestClient, admin_user_factory, monkeypatch) -> None:
        """Health endpoint returns 500 when break is triggered."""
        # Mock migration check to avoid 503 from migrations
        monkeypatch.setattr(
            "jm_api.api.routes.health.assert_database_is_up_to_date", lambda *args, **kwargs: None
        )
        
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        # First verify health is OK
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        
        # Trigger break
        client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Verify health returns 500 with correct error message
        response = client.get("/api/v1/health")
        assert response.status_code == 500
        body = response.json()
        assert body["status"] == "fail"
        assert "artificial health check failure triggered" in body["error"]

    def test_break_causes_ready_to_return_500(self, client: TestClient, admin_user_factory, monkeypatch) -> None:
        """Ready endpoint returns 500 when break is triggered."""
        # Mock migration check to avoid 503 from migrations
        monkeypatch.setattr(
            "jm_api.api.routes.health.assert_database_is_up_to_date", lambda *args, **kwargs: None
        )
        
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        # Trigger break
        client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Verify ready returns 500
        response = client.get("/api/v1/ready")
        assert response.status_code == 500
        body = response.json()
        assert body["status"] == "fail"
        assert "artificial health check failure triggered" in body["error"]

    def test_break_causes_live_to_return_500(self, client: TestClient, admin_user_factory) -> None:
        """Live endpoint returns 500 when break is triggered."""
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        # Trigger break
        client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Verify live returns 500
        response = client.get("/api/v1/live")
        assert response.status_code == 500
        body = response.json()
        assert body["status"] == "fail"
        assert "artificial health check failure triggered" in body["error"]

    def test_break_causes_healthz_to_return_ok(self, client: TestClient, admin_user_factory) -> None:
        """Healthz (legacy) endpoint is NOT affected by break - remains OK."""
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        # Trigger break
        client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Verify healthz still returns 200 (it's a legacy compat endpoint)
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestAdminBreakReset:
    """Verify break reset functionality."""

    def test_admin_can_reset_break(self, client: TestClient, admin_user_factory) -> None:
        """Admin can successfully reset health break."""
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        # First trigger break
        client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Then reset it
        response = client.post(
            "/api/v1/admin/break/reset",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "health break reset"}

    def test_reset_restores_health_endpoint(self, client: TestClient, admin_user_factory, monkeypatch) -> None:
        """Health endpoint returns 200 after break is reset."""
        # Mock migration check to avoid 503 from migrations
        monkeypatch.setattr(
            "jm_api.api.routes.health.assert_database_is_up_to_date", lambda *args, **kwargs: None
        )
        
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        # Trigger break
        client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Verify health returns 500
        response = client.get("/api/v1/health")
        assert response.status_code == 500
        
        # Reset break
        client.post(
            "/api/v1/admin/break/reset",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Verify health returns 200 again
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestAdminBreakStatus:
    """Verify break status endpoint."""

    def test_status_returns_false_when_not_triggered(self, client: TestClient, admin_user_factory) -> None:
        """Status returns triggered: false when break is not active."""
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        response = client.get(
            "/api/v1/admin/break/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"triggered": False}

    def test_status_returns_true_when_triggered(self, client: TestClient, admin_user_factory) -> None:
        """Status returns triggered: true when break is active."""
        admin = admin_user_factory()
        token = _get_access_token(client, admin.email, "password123")
        
        # Trigger break
        client.post(
            "/api/v1/admin/break",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        response = client.get(
            "/api/v1/admin/break/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"triggered": True}


# ===================================================================
# Helper Functions
# ===================================================================

def _get_access_token(client: TestClient, email: str, password: str) -> str:
    """Helper to get an access token for a user."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]
