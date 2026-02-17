from __future__ import annotations

import logging
import logging.config
import random
from collections.abc import Mapping, Sequence
from typing import Any

import structlog

REDACTED_VALUE = "***REDACTED***"
SENSITIVE_FIELD_MARKERS = ("token", "password")
SENSITIVE_FIELD_NAMES = {"password", "password_hash", "access_token", "refresh_token", "token"}


class SamplingFilter(logging.Filter):
    """Sampling filter that always keeps warning/error logs."""

    def __init__(self, sample_rate: float) -> None:
        super().__init__()
        self.sample_rate = sample_rate

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        return random.random() <= self.sample_rate


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in SENSITIVE_FIELD_NAMES:
        return True
    return any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS)


def _redact_nested(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, nested_value in value.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = _redact_nested(nested_value)
        return redacted

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        redacted_items = [_redact_nested(item) for item in value]
        if isinstance(value, tuple):
            return tuple(redacted_items)
        return redacted_items

    return value


def redact_sensitive(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive keys recursively in nested log payloads."""
    return _redact_nested(event_dict)


def configure_logging(level: str, json_logs: bool = True, sample_rate: float = 1.0) -> None:
    """Configure stdlib logging and structlog processors."""
    renderer: structlog.types.Processor
    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        renderer,
    ]

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "sampling": {
                "()": SamplingFilter,
                "sample_rate": sample_rate,
            }
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "filters": ["sampling"],
            }
        },
        "root": {"handlers": ["default"], "level": level.upper()},
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": level.upper(), "propagate": False},
            "uvicorn.error": {
                "handlers": ["default"],
                "level": level.upper(),
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": level.upper(),
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_config)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
