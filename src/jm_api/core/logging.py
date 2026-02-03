from __future__ import annotations

import logging
import logging.config

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str) -> None:
    log_level = level.upper()

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": DEFAULT_LOG_FORMAT},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
            }
        },
        "root": {"handlers": ["default"], "level": log_level},
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": log_level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": log_level, "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": log_level, "propagate": False},
        },
    }

    logging.config.dictConfig(logging_config)
