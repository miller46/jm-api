"""Core modules for JM API."""

from jm_api.core.shutdown import (
    dispose_database_connections,
    drain_connections,
    get_active_request_count,
    graceful_shutdown,
    is_shutting_down,
    register_signal_handlers,
)

__all__ = [
    "dispose_database_connections",
    "drain_connections",
    "get_active_request_count",
    "graceful_shutdown",
    "is_shutting_down",
    "register_signal_handlers",
]
