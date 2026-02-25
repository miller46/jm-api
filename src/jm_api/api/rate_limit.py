from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_address
from time import time
from typing import Any

import structlog
from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from jm_api.api.deps import decode_token
from jm_api.core.config import get_settings
from jm_api.schemas.errors import RateLimitError

SECONDS_PER_UNIT = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "month": 2592000,
}

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class LimitMetadata:
    """Rate limit metadata extracted from a SlowAPI exception."""

    amount: int | None = None
    per: str | None = None
    retry_after_seconds: int | None = None


def _client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                try:
                    ip_address(candidate)
                    return candidate
                except ValueError:
                    return get_remote_address(request)
    return get_remote_address(request)


def _request_tier_and_key(request: Request) -> tuple[str, str]:
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            if payload.type == "access":
                return ("authenticated", f"user:{payload.sub}")
        except Exception:
            # Invalid/expired token should be treated as anonymous for limiting.
            return ("anonymous", f"ip:{_client_ip(request)}")

    return ("anonymous", f"ip:{_client_ip(request)}")


def rate_limit_key_func(request: Request) -> str:
    _tier, key = _request_tier_and_key(request)
    return key


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _coerce_int(value: Any) -> int | None:
    """Best-effort conversion to integer seconds."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            return int(float(value.strip()))
    except (TypeError, ValueError):
        return None
    return None


def _extract_limit_metadata(exc: RateLimitExceeded) -> LimitMetadata:
    """Extract metadata from different SlowAPI exception shapes."""
    amount = _coerce_int(getattr(exc, "amount", None))
    per = getattr(exc, "per", None)
    retry_after_seconds: int | None = None

    if amount is not None and per is not None:
        return LimitMetadata(amount=amount, per=str(per), retry_after_seconds=retry_after_seconds)

    limit_wrapper = getattr(exc, "limit", None)
    limit_item = getattr(limit_wrapper, "limit", None)

    if limit_item is None:
        return LimitMetadata(amount=amount, per=str(per) if per is not None else None)

    if amount is None:
        amount = _coerce_int(getattr(limit_item, "amount", None))

    if per is None:
        granularity_name = getattr(getattr(limit_item, "GRANULARITY", None), "name", None)
        per = str(granularity_name) if granularity_name is not None else None

    get_expiry = getattr(limit_item, "get_expiry", None)
    if callable(get_expiry):
        retry_after_seconds = _coerce_int(get_expiry())

    return LimitMetadata(amount=amount, per=str(per) if per is not None else None, retry_after_seconds=retry_after_seconds)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded errors with consistent payload and headers."""
    settings = get_settings()
    metadata = _extract_limit_metadata(exc)
    tier, _key = _request_tier_and_key(request)

    headers = dict(getattr(exc, "headers", {}) or {})

    retry_after_seconds = metadata.retry_after_seconds
    if retry_after_seconds is None:
        retry_after_seconds = _coerce_int(headers.get("Retry-After"))

    if retry_after_seconds is None and metadata.per is not None:
        retry_after_seconds = SECONDS_PER_UNIT.get(metadata.per.lower())

    if retry_after_seconds is None:
        retry_after_seconds = settings.rate_limit_default_retry_after_seconds

    headers["Retry-After"] = str(retry_after_seconds)

    if metadata.amount is not None:
        headers.setdefault("X-RateLimit-Limit", str(metadata.amount))

    headers.setdefault("X-RateLimit-Remaining", "0")
    headers.setdefault("X-RateLimit-Reset", str(int(time()) + retry_after_seconds))

    logger.warning(
        "rate_limit.exceeded",
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
        limit=metadata.amount,
        tier=tier,
        retry_after=retry_after_seconds,
    )

    payload = RateLimitError(retry_after=retry_after_seconds)
    return JSONResponse(status_code=429, content=payload.model_dump(), headers=headers)


limiter = Limiter(
    key_func=rate_limit_key_func,
    application_limits=[
        f"{_int_env('JM_API_RATE_LIMIT_API_PER_MINUTE', 120)} per minute",
        f"{_int_env('JM_API_RATE_LIMIT_API_PER_HOUR', 3000)} per hour",
        f"{_int_env('JM_API_RATE_LIMIT_QUOTA_PER_DAY', 10000)} per day",
        f"{_int_env('JM_API_RATE_LIMIT_QUOTA_PER_MONTH', 200000)} per month",
    ],
    headers_enabled=True,
    storage_uri=os.getenv("JM_API_RATE_LIMIT_STORAGE_URI", "memory://"),
)
