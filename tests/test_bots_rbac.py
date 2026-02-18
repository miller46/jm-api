"""RBAC tests for bots CRUD write endpoints."""

from fastapi import FastAPI, status
from fastapi.testclient import TestClient


def test_create_bot_requires_auth(app: FastAPI) -> None:
    """Ensure creating a bot requires authentication."""
    unauthenticated_client = TestClient(app)
    response = unauthenticated_client.post("/api/v1/bots", json={"rig_id": "rig-new"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Not authenticated"


def test_create_bot_requires_admin(client: TestClient, user_headers: dict[str, str]) -> None:
    """Ensure non-admin users cannot create bots."""
    response = client.post(
        "/api/v1/bots",
        json={"rig_id": "rig-new"},
        headers=user_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Admin privileges required"


def test_create_bot_allows_admin(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Ensure admin users can create bots."""
    response = client.post(
        "/api/v1/bots",
        json={"rig_id": "rig-new"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED


def test_update_bot_requires_admin(
    client: TestClient,
    bot_factory,
    user_headers: dict[str, str],
) -> None:
    """Ensure non-admin users cannot update bots."""
    bot = bot_factory(rig_id="rig-001")
    response = client.put(
        f"/api/v1/bots/{bot.id}",
        json={"rig_id": "rig-002"},
        headers=user_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Admin privileges required"


def test_delete_bot_requires_admin(
    client: TestClient,
    bot_factory,
    user_headers: dict[str, str],
) -> None:
    """Ensure non-admin users cannot delete bots."""
    bot = bot_factory(rig_id="rig-001")
    response = client.delete(
        f"/api/v1/bots/{bot.id}",
        headers=user_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Admin privileges required"
