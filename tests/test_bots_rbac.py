"""RBAC tests for bots CRUD endpoints."""


from fastapi.testclient import TestClient


def test_create_bot_requires_auth(app) -> None:
    unauthenticated_client = TestClient(app)
    response = unauthenticated_client.post("/api/v1/bots", json={"rig_id": "rig-new"})
    assert response.status_code == 401


def test_create_bot_requires_admin(client, user_headers) -> None:
    response = client.post(
        "/api/v1/bots",
        json={"rig_id": "rig-new"},
        headers=user_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin privileges required"


def test_create_bot_allows_admin(client, admin_headers) -> None:
    response = client.post(
        "/api/v1/bots",
        json={"rig_id": "rig-new"},
        headers=admin_headers,
    )
    assert response.status_code == 201


def test_update_bot_requires_admin(client, bot_factory, user_headers) -> None:
    bot = bot_factory(rig_id="rig-001")
    response = client.put(
        f"/api/v1/bots/{bot.id}",
        json={"rig_id": "rig-002"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_delete_bot_requires_admin(client, bot_factory, user_headers) -> None:
    bot = bot_factory(rig_id="rig-001")
    response = client.delete(
        f"/api/v1/bots/{bot.id}",
        headers=user_headers,
    )
    assert response.status_code == 403
