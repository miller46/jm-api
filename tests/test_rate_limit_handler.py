from types import SimpleNamespace

from starlette.requests import Request

from jm_api.app import rate_limit_exceeded_handler


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_rate_limit_handler_uses_structured_exception_data() -> None:
    exc = SimpleNamespace(amount=100, per="minute", headers={})

    response = rate_limit_exceeded_handler(_request(), exc)  # type: ignore[arg-type]

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] is not None


def test_rate_limit_handler_respects_existing_retry_after_header() -> None:
    exc = SimpleNamespace(amount=100, per="minute", headers={"Retry-After": "30"})

    response = rate_limit_exceeded_handler(_request(), exc)  # type: ignore[arg-type]

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.headers["X-RateLimit-Limit"] == "100"
