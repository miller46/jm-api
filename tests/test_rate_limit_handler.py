"""Tests for rate limit exception handling."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from jm_api.api.rate_limit import rate_limit_exceeded_handler


class _Granularity:
    name: str


class _LimitItem:
    amount: int
    GRANULARITY: _Granularity

    def get_expiry(self) -> object: ...


class _LimitWrapper:
    limit: _LimitItem


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


def _exception_mock(**attrs: object) -> MagicMock:
    """Create a strict mock matching SlowAPI's RateLimitExceeded interface."""
    exc = MagicMock(spec=RateLimitExceeded)
    exc.headers = attrs.get("headers", {})
    exc.amount = attrs.get("amount", None)
    exc.per = attrs.get("per", None)
    exc.limit = attrs.get("limit", None)
    return exc


def _slowapi_limit_wrapper(*, amount: int, per: str, expiry: object) -> MagicMock:
    """Build nested SlowAPI fallback metadata with typed MagicMock specs."""
    granularity = MagicMock(spec=_Granularity)
    granularity.name = per

    limit_item = MagicMock(spec=_LimitItem)
    limit_item.amount = amount
    limit_item.GRANULARITY = granularity
    limit_item.get_expiry.return_value = expiry

    wrapper = MagicMock(spec=_LimitWrapper)
    wrapper.limit = limit_item
    return wrapper


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
    """Handler should read nested SlowAPI metadata when top-level fields are missing."""
    exc = _exception_mock(limit=_slowapi_limit_wrapper(amount=50, per="hour", expiry=3600), headers={})

    response = rate_limit_exceeded_handler(_request(), exc)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"
    assert response.headers["X-RateLimit-Limit"] == "50"
    assert json.loads(response.body)["retry_after"] == 3600


def test_rate_limit_handler_handles_non_integer_expiry() -> None:
    """Non-integer expiry values should safely fall back to per-unit defaults."""
    exc = _exception_mock(limit=_slowapi_limit_wrapper(amount=50, per="minute", expiry="not-an-int"), headers={})

    response = rate_limit_exceeded_handler(_request(), exc)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert json.loads(response.body)["retry_after"] == 60


def test_rate_limit_handler_parses_http_date_retry_after() -> None:
    """HTTP-date Retry-After headers should be converted to delta seconds."""
    retry_after_date = (datetime.now(timezone.utc) + timedelta(seconds=90)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    exc = _exception_mock(headers={"Retry-After": retry_after_date})

    response = rate_limit_exceeded_handler(_request(), exc)

    retry_after = int(response.headers["Retry-After"])
    assert response.status_code == 429
    assert 0 <= retry_after <= 90
    assert json.loads(response.body)["retry_after"] == retry_after


def test_rate_limit_handler_defaults_when_fallback_shape_missing() -> None:
    """Missing SlowAPI metadata should still produce a valid default 429 payload."""
    exc = _exception_mock(headers={})

    response = rate_limit_exceeded_handler(_request(), exc)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert json.loads(response.body)["retry_after"] == 60
