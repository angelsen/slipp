"""Secret pull sources registry."""

from slipp.services.secrets.sources import nor_auth as _nor_auth  # Register sources
from slipp.services.secrets.sources.base import (
    SOURCES,
    PullSession,
    SecretSource,
    find_available_port,
    get_source,
    list_sources,
    register_source,
)

del _nor_auth  # Clean up namespace

__all__ = [
    "PullSession",
    "SecretSource",
    "SOURCES",
    "find_available_port",
    "get_source",
    "list_sources",
    "register_source",
]
