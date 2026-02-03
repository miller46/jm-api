from fastapi.testclient import TestClient

from jm_api.app import create_app


def test_health_check_returns_ok_and_request_id() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers
