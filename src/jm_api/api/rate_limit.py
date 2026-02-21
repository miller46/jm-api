from __future__ import annotations

import os
from ipaddress import ip_address

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from jm_api.api.deps import decode_token
from jm_api.core.config import get_settings


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
