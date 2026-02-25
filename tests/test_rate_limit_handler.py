"""Tests for rate limit exception handling."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from jm_api.api.rate_limit import rate_limit_exceeded_handler


def _request() -> Request:
    """Build a synthetic Starlette request for handler tests."""
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


def _exception_mock(**attrs: object) -> RateLimitExceeded:
    """Create a typed mock matching SlowAPI's RateLimitExceeded interface."""
    exc = Mock(spec=RateLimitExceeded)
    exc.headers = attrs.get("headers", {})
    exc.amount = attrs.get("amount", None)
    exc.per = attrs.get("per", None)
    exc.limit = attrs.get("limit", None)
    return exc


def test_rate_limit_handler_uses_structured_exception_data() -> None:
    """Handler should use amount/per values when present on exception."""
    exc = _exception_mock(amount=100, per="minute", headers={})

    response = rate_limit_exceeded_handler(_request(), exc)

    assert response.status_code == 429
    assert json.loads(response.body) == {
        "detail": "Rate limit exceeded. Please try again later.",
        "retry_after": 60,
    }
    assert response.headers["Retry-After"] == "60"
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] is not None


def test_rate_limit_handler_respects_existing_retry_after_header() -> None:
    """Explicit Retry-After from middleware should take precedence."""
    exc = _exception_mock(amount=100, per="minute", headers={"Retry-After": "30"})

    response = rate_limit_exceeded_handler(_request(), exc)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert json.loads(response.body)["retry_after"] == 30


def test_rate_limit_handler_uses_slowapi_fallback_shape() -> None:
    """Handler should read nested SlowAPI limit metadata when top-level fields are missing."""
    limit_item = SimpleNamespace(
        amount=50,
        GRANULARITY=SimpleNamespace(name="hour"),
        get_expiry=lambda: 3600,
    )
    exc = _exception_mock(limit=SimpleNamespace(limit=limit_item), headers={})

    response = rate_limit_exceeded_handler(_request(), exc)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"
    assert response.headers["X-RateLimit-Limit"] == "50"
    assert json.loads(response.body)["retry_after"] == 3600


def test_rate_limit_handler_handles_non_integer_expiry() -> None:
    """Non-integer expiry values should safely fall back to per-unit defaults."""
    limit_item = SimpleNamespace(
        amount=50,
        GRANULARITY=SimpleNamespace(name="minute"),
        get_expiry=lambda: "not-an-int",
    )
    exc = _exception_mock(limit=SimpleNamespace(limit=limit_item), headers={})

    response = rate_limit_exceeded_handler(_request(), exc)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert json.loads(response.body)["retry_after"] == 60
