"""Tests for Bot create (POST) API endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestCreateBotSuccess:
    """Test POST /api/v1/bots creates a record."""

    def test_create_bot_returns_201(self, client: TestClient) -> None:
        """Successful creation returns 201 status code."""
        response = client.post("/api/v1/bots", json={"rig_id": "rig-new"})
        assert response.status_code == 201

    def test_create_bot_returns_all_fields(self, client: TestClient) -> None:
        """Created bot response includes all BotResponse fields."""
        response = client.post("/api/v1/bots", json={"rig_id": "rig-new"})
        data = response.json()
        expected_fields = {
            "id",
            "rig_id",
            "last_run_at",
            "kill_switch",
            "last_run_log",
            "create_at",
            "last_update_at",
        }
        assert set(data.keys()) == expected_fields

    def test_create_bot_defaults(self, client: TestClient) -> None:
        """Created bot has correct defaults for optional fields."""
        response = client.post("/api/v1/bots", json={"rig_id": "rig-new"})
        data = response.json()
        assert data["rig_id"] == "rig-new"
        assert data["kill_switch"] is False
        assert data["last_run_at"] is None

    def test_create_bot_with_all_fields(self, client: TestClient) -> None:
        """Create bot with all user-editable fields set."""
        payload = {
            "rig_id": "rig-full",
            "kill_switch": True,
            "last_run_log": "initial log",
        }
        response = client.post("/api/v1/bots", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["rig_id"] == "rig-full"
        assert data["kill_switch"] is True
        assert data["last_run_log"] == "initial log"

    def test_create_bot_persisted(self, client: TestClient) -> None:
        """Created bot can be retrieved via GET."""
        response = client.post("/api/v1/bots", json={"rig_id": "rig-persist"})
        assert response.status_code == 201
        bot_id = response.json()["id"]

        get_response = client.get(f"/api/v1/bots/{bot_id}")
        assert get_response.status_code == 200
        assert get_response.json()["rig_id"] == "rig-persist"

    def test_create_bot_auto_fields_generated(self, client: TestClient) -> None:
        """Auto-managed fields (id, create_at, last_update_at) are set automatically."""
        response = client.post("/api/v1/bots", json={"rig_id": "rig-auto"})
        data = response.json()
        assert data["id"] is not None
        assert len(data["id"]) == 32
        assert data["create_at"] is not None
        assert data["last_update_at"] is not None


class TestCreateBotValidation:
    """Test POST /api/v1/bots validation errors."""

    def test_create_bot_missing_rig_id(self, client: TestClient) -> None:
        """Missing required rig_id returns 422."""
        response = client.post("/api/v1/bots", json={})
        assert response.status_code == 422

    def test_create_bot_empty_body(self, client: TestClient) -> None:
        """Empty request body returns 422."""
        response = client.post(
            "/api/v1/bots",
            content="",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_create_bot_ignores_auto_fields(self, client: TestClient) -> None:
        """Passing auto-managed fields in body does not override them."""
        payload = {
            "rig_id": "rig-ignore",
            "id": "custom_id_should_be_ignored_xxxxx",
        }
        response = client.post("/api/v1/bots", json=payload)
        assert response.status_code == 201
        data = response.json()
        # id should be auto-generated, not the one we passed
        assert data["id"] != "custom_id_should_be_ignored_xxxxx"


class TestBotOpenAPICreateSchema:
    """Test that the OpenAPI spec exposes BotCreate schema fields correctly.

    The frontend form uses the OpenAPI schema to discover editable fields,
    so the schema must only contain user-editable fields (no auto-managed ones).
    """

    def test_openapi_has_bot_create_schema(self, client: TestClient) -> None:
        """OpenAPI spec includes BotCreate schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        schemas = schema.get("components", {}).get("schemas", {})
        assert "BotCreate" in schemas

    def test_bot_create_schema_has_only_editable_fields(
        self, client: TestClient
    ) -> None:
        """BotCreate schema contains only user-editable fields, not auto-managed ones."""
        response = client.get("/openapi.json")
        schema = response.json()
        bot_create = schema["components"]["schemas"]["BotCreate"]
        props = set(bot_create.get("properties", {}).keys())
        # Only user-editable fields should be present
        assert props == {"rig_id", "kill_switch", "last_run_log"}

    def test_bot_create_schema_excludes_auto_fields(
        self, client: TestClient
    ) -> None:
        """BotCreate schema does not contain auto-managed fields."""
        response = client.get("/openapi.json")
        schema = response.json()
        bot_create = schema["components"]["schemas"]["BotCreate"]
        props = set(bot_create.get("properties", {}).keys())
        auto_fields = {"id", "create_at", "last_update_at", "last_run_at"}
        assert props.isdisjoint(auto_fields), (
            f"Auto-managed fields found in BotCreate schema: {props & auto_fields}"
        )

    def test_post_bots_endpoint_references_create_schema(
        self, client: TestClient
    ) -> None:
        """POST /api/v1/bots references BotCreate as request body schema."""
        response = client.get("/openapi.json")
        schema = response.json()
        post_path = schema.get("paths", {}).get("/api/v1/bots", {}).get("post", {})
        req_body = post_path.get("requestBody", {})
        json_schema = (
            req_body.get("content", {}).get("application/json", {}).get("schema", {})
        )
        ref = json_schema.get("$ref", "")
        assert "BotCreate" in ref
