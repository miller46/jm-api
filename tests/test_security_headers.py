from __future__ import annotations

from fastapi.testclient import TestClient

from jm_api.app import create_app
from jm_api.core.config import get_settings


def test_security_headers_are_set_on_api_responses() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/live")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_admin_csp_is_set_for_admin_routes() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/admin/index.html")

    assert response.status_code == 200
    assert "content-security-policy" in response.headers
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_security_headers_can_be_configured_via_env(monkeypatch) -> None:
    monkeypatch.setenv("JM_API_SECURITY_HEADER_X_FRAME_OPTIONS", "SAMEORIGIN")
    monkeypatch.setenv("JM_API_SECURITY_HEADER_HSTS_MAX_AGE", "86400")
    monkeypatch.setenv("JM_API_SECURITY_HEADER_HSTS_INCLUDE_SUBDOMAINS", "false")
    monkeypatch.setenv("JM_API_SECURITY_HEADER_HSTS_PRELOAD", "true")
    monkeypatch.setenv("JM_API_SECURITY_HEADER_ADMIN_CSP", "default-src 'self'; frame-ancestors 'none';")
    get_settings.cache_clear()

    app = create_app()

    with TestClient(app) as client:
        api_response = client.get("/api/v1/live")
        admin_response = client.get("/admin/index.html")

    assert api_response.headers["x-frame-options"] == "SAMEORIGIN"
    assert api_response.headers["strict-transport-security"] == "max-age=86400; preload"
    assert admin_response.headers["content-security-policy"] == "default-src 'self'; frame-ancestors 'none';"

    get_settings.cache_clear()
