from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from jm_api.core.config import get_settings
from jm_api.middleware.request_size_limit import RequestSizeLimitMiddleware


def _build_test_app(limit: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=limit)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"size": len(body)}

    return app


def test_request_body_within_limit_is_accepted() -> None:
    app = _build_test_app(limit=16)

    with TestClient(app) as client:
        response = client.post("/echo", content=b"1234567890")

    assert response.status_code == 200
    assert response.json() == {"size": 10}


def test_request_body_over_limit_returns_413() -> None:
    app = _build_test_app(limit=8)

    with TestClient(app) as client:
        response = client.post("/echo", content=b"123456789")

    assert response.status_code == 413
    assert response.json() == {"detail": "Payload Too Large"}


def test_logs_rejected_request_with_size_info() -> None:
    app = _build_test_app(limit=8)

    with patch("jm_api.middleware.request_size_limit.logger.warning") as warning_mock:
        with TestClient(app) as client:
            response = client.post("/echo", content=b"123456789")

    assert response.status_code == 413
    warning_mock.assert_called_once()
    _, kwargs = warning_mock.call_args
    assert kwargs["content_length"] == 9
    assert kwargs["max_body_bytes"] == 8


def test_max_request_body_bytes_is_configurable_via_environment(monkeypatch) -> None:
    monkeypatch.setenv("JM_API_MAX_REQUEST_BODY_BYTES", "1234")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.max_request_body_bytes == 1234

    get_settings.cache_clear()
