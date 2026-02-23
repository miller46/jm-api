#!/usr/bin/env python3
"""Worker CLI entry point for running background tasks."""

from __future__ import annotations

import logging
import sys

from jm_api.core.config import get_settings
from jm_api.core.logging import configure_logging
from jm_api.services.worker import TaskWorker

def main() -> int:
    """Run the background task worker."""
    settings = get_settings()
    configure_logging(
        settings.log_level,
        json_logs=settings.log_json,
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting background task worker")

    worker = TaskWorker()

    # TODO: Register actual task handlers here
    # Example:
    # @worker.register_handler
    # def email_send(payload: dict) -> dict:
    #     # Implementation here
    #     pass

    try:
        worker.run()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as exc:
        logger.exception(f"Worker crashed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
