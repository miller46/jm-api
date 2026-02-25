"""Error response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class RateLimitError(BaseModel):
    """Standard 429 rate limit error payload."""

    detail: str = "Rate limit exceeded. Please try again later."
    retry_after: int
