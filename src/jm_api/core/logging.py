from __future__ import annotations

import logging
import logging.config
import random
from typing import Any

import structlog


class SamplingFilter(logging.Filter):
    def __init__(self, sample_rate: float) -> None:
        super().__init__()
        self.sample_rate = sample_rate

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        return random.random() <= self.sample_rate


def redact_sensitive(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    redacted_fields = {"password", "password_hash", "access_token", "refresh_token", "token"}
    for key in list(event_dict.keys()):
        lowered = key.lower()
        if lowered in redacted_fields or "token" in lowered or "password" in lowered:
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_logging(level: str, json_logs: bool = True, sample_rate: float = 1.0) -> None:
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
